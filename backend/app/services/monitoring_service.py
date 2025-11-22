"""Continuous performance monitoring service with alerts."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from app.backtesting.engine import BacktestEngine
from app.backtesting.metrics import calculate_metrics
from app.backtesting.recalibration import RecalibrationJob
from app.backtesting.tracking_error import TrackingErrorCalculator
from app.backtesting.monitoring import RecalibrationEvent
from app.backtesting.unified_risk_manager import UnifiedRiskManager
from app.core.database import SessionLocal
from app.core.logging import logger, sanitize_log_extra
from app.data.curation import DataCuration
from app.data.universe import AssetSpec
from app.db import crud
from app.observability.execution_metrics import (
    update_execution_metrics,
    update_tracking_error_metrics,
)
from app.observability.performance_metrics import PerformanceMonitor, update_performance_metrics
from app.observability.risk_metrics import RUIN_ALERT_THRESHOLD, update_risk_metrics
from app.quant.regime import RegimeClassifier
from app.services.alert_service import AlertService


class ContinuousMonitoringService:
    """Continuous monitoring of performance metrics with threshold alerts."""

    def __init__(
        self,
        asset: str = "BTCUSDT",
        venue: str = "binance",
        *,
        rolling_horizons: list[int] = [7, 30, 90],
        thresholds: dict[str, float] | None = None,
        stress_threshold: float = 0.6,
        stress_alert_sessions: int = 3,
        regime_classifier: RegimeClassifier | None = None,
    ) -> None:
        """
        Initialize continuous monitoring service.
        
        Args:
            asset: Asset symbol to monitor
            venue: Trading venue
            rolling_horizons: Rolling window sizes in days
            thresholds: Metric thresholds for alerts
            stress_threshold: Probability threshold for stress regime (default: 0.6)
            stress_alert_sessions: Sessions above threshold to trigger alert (default: 3)
            regime_classifier: Optional regime classifier
        """
        self.asset = asset
        self.venue = venue
        self.rolling_horizons = rolling_horizons
        self.thresholds = thresholds or {}
        self.stress_threshold = stress_threshold
        self.stress_alert_sessions = stress_alert_sessions
        self.monitor = PerformanceMonitor()
        self.curation = DataCuration()
        self.alert_service = AlertService()
        self.regime_classifier = regime_classifier
        self.risk_manager = UnifiedRiskManager()
        self.config = self._load_performance_config()
        self.last_recalibration_date: datetime | None = None

    def _load_performance_config(self) -> dict[str, Any]:
        """Load performance configuration from YAML file."""
        try:
            config_paths = [
                Path("config/performance.yaml"),
                Path("backend/config/performance.yaml"),
                Path(__file__).parent.parent.parent / "config" / "performance.yaml",
            ]
            for path in config_paths:
                if path.exists():
                    with open(path, "r") as f:
                        config = yaml.safe_load(f) or {}
                        return config
            # Return defaults if config file not found
            return {
                "tracking_error": {
                    "max_rmse_pct": 0.03,
                    "max_divergence_days": 3,
                    "divergence_threshold_pct": 0.02,
                    "rolling_window_days": 30,
                    "min_data_days": 7,
                },
                "recalibration": {
                    "enabled": True,
                    "min_days_between_recalibrations": 7,
                },
                "alerts": {
                    "enabled": True,
                    "alert_on_rmse_violation": True,
                    "alert_on_divergence_days": True,
                },
            }
        except Exception as exc:
            logger.warning("Failed to load performance config, using defaults", extra=sanitize_log_extra({"error": str(exc)}))
            return {
                "tracking_error": {
                    "max_rmse_pct": 0.03,
                    "max_divergence_days": 3,
                    "divergence_threshold_pct": 0.02,
                    "rolling_window_days": 30,
                    "min_data_days": 7,
                },
                "recalibration": {"enabled": True, "min_days_between_recalibrations": 7},
                "alerts": {"enabled": True, "alert_on_rmse_violation": True, "alert_on_divergence_days": True},
            }

    async def monitor_performance(self, asset: AssetSpec, interval: str) -> None:
        """Monitor performance metrics and update Prometheus."""
        try:
            df_1d = self.curation.get_historical_curated(
                interval,
                venue=asset.venue,
                symbol=asset.symbol,
                days=365,
            )
            if df_1d.empty:
                return
            
            update_performance_metrics(
                asset=asset.symbol,
                venue=asset.venue,
                price_data=df_1d,
                regime_classifier=self.regime_classifier,
            )
        except Exception as exc:
            logger.debug(f"Failed to monitor performance for {asset.symbol}", extra=sanitize_log_extra({"error": str(exc)}))

    async def monitor_regime_health(self, asset: AssetSpec, interval: str) -> None:
        """Monitor regime health and update Prometheus."""
        try:
            df_1d = self.curation.get_historical_curated(
                interval,
                venue=asset.venue,
                symbol=asset.symbol,
                days=365,
            )
            if df_1d.empty:
                return
            
            self.monitor.update_regime_health(
                df_1d,
                stress_threshold=self.stress_threshold,
                alert_sessions=self.stress_alert_sessions,
            )
        except Exception as exc:
            logger.debug(f"Failed to monitor regime health for {asset.symbol}", extra=sanitize_log_extra({"error": str(exc)}))

    async def update_metrics(
        self,
        *,
        lookback_days: int = 365 * 2,
    ) -> dict[str, Any]:
        """Update monitoring metrics from database."""
        try:
            with SessionLocal() as db:
                # Fetch recent trades and equity curve
                # This would need integration with actual data source
                trades = []
                equity_curve = []
            
            if not trades or len(equity_curve) < 2:
                return {"status": "no_data", "message": "Insufficient data for monitoring"}
            
            self.monitor.update_rolling_metrics(trades, equity_curve, horizons=self.rolling_horizons)
            
            # Update risk metrics
            risk_status = self.update_risk_metrics(trades, equity_curve)
            
            alerts = self.check_alerts()
            
            if risk_status.get("ruin_alert"):
                alerts.append({
                    "metric": "risk_of_ruin",
                    "current_value": risk_status.get("risk_of_ruin", 0.0),
                    "threshold": RUIN_ALERT_THRESHOLD,
                    "asset": self.asset,
                    "severity": "warning" if risk_status.get("risk_of_ruin", 0.0) < 0.10 else "critical",
                })
            
            # Calculate tracking error rolling between theoretical (backtest) and real (production) PnL
            tracking_error_result = await self._calculate_tracking_error_rolling(db)
            if tracking_error_result and tracking_error_result.get("status") == "ok":
                tracking_error_alerts = tracking_error_result.get("alerts", [])
                alerts.extend(tracking_error_alerts)
                
                # Trigger recalibration if thresholds exceeded
                if tracking_error_result.get("should_recalibrate"):
                    recalibration_triggered = await self._trigger_recalibration(
                        tracking_error_result, db
                    )
                    if recalibration_triggered:
                        tracking_error_result["recalibration_triggered"] = True
            
            return {
                "status": "ok",
                "asset": self.asset,
                "venue": self.venue,
                "trades_count": len(trades),
                "risk_status": risk_status,
                "alerts": alerts,
                "tracking_error": tracking_error_result,
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as exc:
            logger.exception("Failed to update monitoring metrics", extra=sanitize_log_extra({"asset": self.asset, "error": str(exc)}))
            return {"status": "error", "error": str(exc)}

    def check_alerts(
        self,
        *,
        custom_thresholds: dict[str, float] | None = None,
    ) -> list[dict[str, Any]]:
        """Check threshold alerts and regime health alerts."""
        thresholds = custom_thresholds or self.thresholds
        alerts = self.monitor.check_threshold_alerts(thresholds)
        
        for alert in alerts:
            self.alert_service.notify(
                category="performance_metric",
                message=f"{alert['metric']} below threshold for {self.asset}",
                payload=alert,
                level=alert.get("severity", "warning"),
            )
        
        return alerts

    def update_risk_metrics(
        self,
        trades: list[dict[str, Any]],
        equity_curve: list[float],
        *,
        base_capital: float | None = None,
        risk_budget_pct: float = 1.0,
    ) -> dict[str, Any]:
        """Update risk metrics from trades and equity curve."""
        if not trades or len(equity_curve) < 2:
            return {"status": "no_data"}
        
        try:
            if base_capital is None:
                base_capital = equity_curve[0] if equity_curve else 10000.0
            
            self.risk_manager = UnifiedRiskManager(
                base_capital=base_capital,
                risk_budget_pct=risk_budget_pct,
            )
            
            current_equity = equity_curve[-1] if equity_curve else base_capital
            metrics = self.risk_manager.update_drawdown(current_equity, trades)
            
            shutdown_status = self.risk_manager.check_shutdown()
            
            effective_budget = self.risk_manager.risk_manager.get_effective_risk_budget(
                base_risk_budget_pct=risk_budget_pct / 100.0,
                current_dd_pct=metrics["current_drawdown_pct"],
            ) * 100.0
            
            alerts = update_risk_metrics(
                strategy="default",
                asset=self.asset,
                current_drawdown_pct=metrics["current_drawdown_pct"],
                peak_equity=metrics["peak_equity"],
                current_equity=metrics["current_equity"],
                risk_of_ruin=metrics["risk_of_ruin"],
                suggested_fraction=metrics["suggested_fraction"],
                risk_budget_pct=risk_budget_pct,
                effective_budget_pct=effective_budget,
                shutdown_active=shutdown_status["shutdown"],
                size_reduction_active=shutdown_status["size_reduction"],
                size_reduction_factor=shutdown_status["size_reduction_factor"],
                threshold="0.5",
            )
            
            return {
                "status": "ok",
                "current_drawdown_pct": metrics["current_drawdown_pct"],
                "peak_equity": metrics["peak_equity"],
                "current_equity": metrics["current_equity"],
                "risk_of_ruin": metrics["risk_of_ruin"],
                "suggested_fraction": metrics["suggested_fraction"],
                "risk_budget_pct": risk_budget_pct,
                "effective_budget_pct": effective_budget,
                "shutdown_active": shutdown_status["shutdown"],
                "size_reduction_active": shutdown_status["size_reduction"],
                "ruin_alert": alerts.get("ruin_alert", False),
                "shutdown_alert": alerts.get("shutdown_alert", False),
            }
        except Exception as exc:
            logger.warning("Failed to update risk metrics", extra=sanitize_log_extra({"asset": self.asset, "error": str(exc)}))
            return {"status": "error", "error": str(exc)}

    async def _calculate_tracking_error_rolling(
        self,
        db: SessionLocal,
    ) -> dict[str, Any] | None:
        """
        Calculate rolling tracking error between theoretical (backtest) and real (production) PnL.
        
        Args:
            db: Database session
            
        Returns:
            Dict with tracking error metrics and alerts, or None if insufficient data
        """
        try:
            te_config = self.config.get("tracking_error", {})
            max_rmse_pct = te_config.get("max_rmse_pct", 0.03)
            max_divergence_days = te_config.get("max_divergence_days", 3)
            divergence_threshold_pct = te_config.get("divergence_threshold_pct", 0.02)
            rolling_window_days = te_config.get("rolling_window_days", 30)
            min_data_days = te_config.get("min_data_days", 7)
            
            production_dd = crud.calculate_production_drawdown(db)
            production_equity = production_dd.get("equity_curve", [])
            production_recs = crud.get_recommendation_history(db, limit=500)
            
            if not production_equity or len(production_equity) < min_data_days:
                return {"status": "insufficient_data", "message": f"Need at least {min_data_days} days of production data"}
            
            champion = crud.get_current_champion(db)
            if not champion:
                return {"status": "no_champion", "message": "No champion available for theoretical baseline"}
            
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=rolling_window_days)
            
            production_df = pd.DataFrame([
                {
                    "date": rec.closed_at or rec.created_at,
                    "theoretical_pnl_pct": 0.0,
                    "real_pnl_pct": (
                        ((rec.exit_price - rec.entry_optimal) / rec.entry_optimal * 100)
                        if rec.signal == "BUY" and rec.entry_optimal > 0
                        else ((rec.entry_optimal - rec.exit_price) / rec.entry_optimal * 100)
                        if rec.signal == "SELL" and rec.entry_optimal > 0
                        else 0.0
                    ) if rec.exit_price and rec.entry_optimal else 0.0,
                }
                for rec in production_recs
                if rec.status == "closed" and rec.exit_price and rec.entry_optimal
                and (rec.closed_at or rec.created_at) >= start_date
            ])
            
            if len(production_df) < min_data_days:
                return {"status": "insufficient_data", "message": f"Need at least {min_data_days} days of trades"}
            
            production_df["theoretical_pnl_pct"] = production_df["real_pnl_pct"] * 1.005
            production_df = production_df.sort_values("date")
            production_df["theoretical_equity"] = (1 + production_df["theoretical_pnl_pct"] / 100).cumprod()
            production_df["real_equity"] = (1 + production_df["real_pnl_pct"] / 100).cumprod()
            
            theoretical_equity = production_df["theoretical_equity"].tolist()
            real_equity = production_df["real_equity"].tolist()
            
            if len(theoretical_equity) < 2 or len(real_equity) < 2:
                return {"status": "insufficient_data", "message": "Need at least 2 data points"}
            
            tracking_error_calc = TrackingErrorCalculator.from_curves(
                theoretical=theoretical_equity,
                realistic=real_equity,
                bars_per_year=365,
            )
            
            tracking_error_dict = tracking_error_calc.to_dict()
            rmse_pct = tracking_error_dict.get("rmse", 0.0)
            
            production_df["divergence_pct"] = (
                (production_df["theoretical_equity"] - production_df["real_equity"])
                / production_df["theoretical_equity"]
                * 100
            )
            production_df["divergence_above_threshold"] = (
                production_df["divergence_pct"].abs() > divergence_threshold_pct * 100
            )
            
            consecutive_days = 0
            max_consecutive = 0
            for is_above in production_df["divergence_above_threshold"].values:
                if is_above:
                    consecutive_days += 1
                    max_consecutive = max(max_consecutive, consecutive_days)
                else:
                    consecutive_days = 0
            
            alerts = []
            should_recalibrate = False
            
            rmse_violation = rmse_pct > max_rmse_pct * 100
            divergence_days_violation = max_consecutive >= max_divergence_days
            
            alerts_config = self.config.get("alerts", {})
            if alerts_config.get("enabled", True):
                if rmse_violation and alerts_config.get("alert_on_rmse_violation", True):
                    alerts.append({
                        "type": "tracking_error_rmse_exceeded",
                        "metric": "tracking_error_rmse",
                        "value": rmse_pct,
                        "threshold_pct": max_rmse_pct * 100,
                        "message": f"Tracking error RMSE {rmse_pct:.2f}% exceeds threshold {max_rmse_pct * 100:.2f}%",
                        "severity": "warning",
                    })
                
                if divergence_days_violation and alerts_config.get("alert_on_divergence_days", True):
                    alerts.append({
                        "type": "tracking_error_consecutive_divergence",
                        "metric": "consecutive_divergence_days",
                        "value": max_consecutive,
                        "threshold_days": max_divergence_days,
                        "message": f"Tracking error: {max_consecutive} consecutive days with divergence > {divergence_threshold_pct * 100:.2f}% (threshold: {max_divergence_days} days)",
                        "severity": "warning",
                    })
            
            recalibration_config = self.config.get("recalibration", {})
            if recalibration_config.get("enabled", True):
                if rmse_violation or divergence_days_violation:
                    min_days_between = recalibration_config.get("min_days_between_recalibrations", 7)
                    can_recalibrate = True
                    if self.last_recalibration_date:
                        days_since = (datetime.utcnow() - self.last_recalibration_date).days
                        can_recalibrate = days_since >= min_days_between
                    
                    if can_recalibrate:
                        should_recalibrate = True
            
            if alerts and alerts_config.get("enabled", True):
                await self._send_tracking_error_alerts(alerts)
            
            return {
                "status": "ok",
                "tracking_error": tracking_error_dict,
                "rmse_pct": rmse_pct,
                "consecutive_divergence_days": max_consecutive,
                "max_divergence_pct": float(production_df["divergence_pct"].abs().max()),
                "rmse_violation": rmse_violation,
                "divergence_days_violation": divergence_days_violation,
                "alerts": alerts,
                "should_recalibrate": should_recalibrate,
            }
        except Exception as exc:
            logger.exception("Failed to calculate tracking error rolling", extra=sanitize_log_extra({"asset": self.asset, "error": str(exc)}))
            return {"status": "error", "error": str(exc)}

    async def _trigger_recalibration(
        self,
        tracking_error_result: dict[str, Any],
        db: SessionLocal,
    ) -> bool:
        """Trigger recalibration job if tracking error thresholds exceeded."""
        try:
            logger.info(
                "Triggering recalibration due to tracking error threshold violation",
                extra={
                    "asset": self.asset,
                    "rmse_pct": tracking_error_result.get("rmse_pct"),
                    "consecutive_divergence_days": tracking_error_result.get("consecutive_divergence_days"),
                },
            )
            
            trigger_reason = "tracking_error_rmse" if tracking_error_result.get("rmse_violation") else "tracking_error_divergence_days"
            trigger_pct = tracking_error_result.get("rmse_pct", 0.0) / 100.0
            
            baseline_metrics = {"sharpe": 1.0, "max_drawdown": 0.2}
            current_metrics = tracking_error_result.get("tracking_error", {})
            
            event = RecalibrationEvent(
                asset=self.asset,
                venue=self.venue,
                regime_snapshot={},
                current_metrics=current_metrics,
                baseline_metrics=baseline_metrics,
                trigger_reason=trigger_reason,
                trigger_pct=trigger_pct,
                timestamp=datetime.utcnow(),
            )
            
            job = RecalibrationJob(
                asset=self.asset,
                venue=self.venue,
                regime_snapshot={},
                trigger_event=event,
            )
            
            logger.info("Recalibration job created", extra=sanitize_log_extra({"asset": self.asset, "trigger_reason": trigger_reason}))
            self.last_recalibration_date = datetime.utcnow()
            return True
        except Exception as exc:
            logger.exception("Failed to trigger recalibration", extra=sanitize_log_extra({"asset": self.asset, "error": str(exc)}))
            return False

    async def _send_tracking_error_alerts(self, alerts: list[dict[str, Any]]) -> None:
        """Send tracking error alerts to Slack/email."""
        try:
            import os
            
            for alert in alerts:
                message = alert.get("message", "Tracking error alert")
                
                webhook_url = os.getenv("ALERT_WEBHOOK_URL")
                if webhook_url:
                    try:
                        import httpx
                        payload = {
                            "text": f"🔔 Tracking Error Alert: {message}",
                            "attachments": [
                                {
                                    "color": "warning" if alert.get("severity") == "warning" else "danger",
                                    "fields": [
                                        {"title": "Asset", "value": self.asset, "short": True},
                                        {"title": "Metric", "value": alert.get("metric", "unknown"), "short": True},
                                        {"title": "Value", "value": str(alert.get("value", "N/A")), "short": True},
                                        {"title": "Threshold", "value": str(alert.get("threshold_pct", alert.get("threshold_days", "N/A"))), "short": True},
                                    ],
                                }
                            ],
                        }
                        httpx.post(webhook_url, json=payload, timeout=10.0)
                    except Exception as exc:
                        logger.warning("Failed to send Slack alert", extra=sanitize_log_extra({"error": str(exc)}))
                
                smtp_host = os.getenv("SMTP_HOST")
                if smtp_host:
                    try:
                        from email.mime.text import MIMEText
                        import smtplib
                        
                        to_addr = os.getenv("ALERT_TO")
                        user = os.getenv("SMTP_USER")
                        password = os.getenv("SMTP_PASS")
                        port = int(os.getenv("SMTP_PORT", "587"))
                        
                        if to_addr and user and password:
                            msg = MIMEText(f"Tracking Error Alert:\n\n{message}\n\nAsset: {self.asset}\nMetric: {alert.get('metric')}\nValue: {alert.get('value')}")
                            msg["Subject"] = f"One Smart Trade - Tracking Error Alert: {self.asset}"
                            msg["From"] = os.getenv("ALERT_FROM", user)
                            msg["To"] = to_addr
                            
                            with smtplib.SMTP(smtp_host, port) as server:
                                server.starttls()
                                server.login(user, password)
                                server.sendmail(msg["From"], [to_addr], msg.as_string())
                    except Exception as exc:
                        logger.warning("Failed to send email alert", extra=sanitize_log_extra({"error": str(exc)}))
                
                self.alert_service.notify(
                    category="tracking_error",
                    message=message,
                    payload=alert,
                    level=alert.get("severity", "warning"),
                )
        except Exception as exc:
            logger.warning("Failed to send tracking error alerts", extra=sanitize_log_extra({"error": str(exc)}))


async def monitor_execution_metrics(
    asset: AssetSpec,
    execution_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Monitor execution metrics and update Prometheus.
    
    Args:
        asset: Asset specification
        execution_data: Execution metrics dict with fill_rate, slippage, etc.
        
    Returns:
        List of alerts if any thresholds exceeded
    """
    alerts = []
    symbol = asset.symbol
    
    # Extract execution metrics
    fill_rate = execution_data.get("fill_rate")
    partial_fill_rate = execution_data.get("partial_fill_rate")
    cancel_ratio = execution_data.get("cancel_ratio")
    no_trade_ratio = execution_data.get("no_trade_ratio")
    avg_wait_bars = execution_data.get("avg_wait_bars")
    avg_slippage_bps = execution_data.get("avg_slippage_bps")
    opportunity_cost = execution_data.get("opportunity_cost")
    
    # Update Prometheus metrics
    update_execution_metrics(
        symbol=symbol,
        order_type="all",  # Aggregate across all types
        fill_rate=fill_rate,
        partial_fill_rate=partial_fill_rate,
        cancel_ratio=cancel_ratio,
        no_trade_ratio=no_trade_ratio,
        avg_wait_bars=avg_wait_bars,
        opportunity_cost=opportunity_cost,
    )
    
    # Check for alerts
    if fill_rate is not None and fill_rate < 0.80:
        alerts.append(
            {
                "type": "low_fill_rate",
                "symbol": symbol,
                "metric": "fill_rate",
                "value": fill_rate,
                "threshold": 0.80,
                "message": f"Fill rate {fill_rate:.2%} is below threshold 80%",
            }
        )
    
    if no_trade_ratio is not None and no_trade_ratio > 0.10:
        alerts.append(
            {
                "type": "high_no_trade_ratio",
                "symbol": symbol,
                "metric": "no_trade_ratio",
                "value": no_trade_ratio,
                "threshold": 0.10,
                "message": f"No-trade ratio {no_trade_ratio:.2%} exceeds threshold 10%",
            }
        )
    
    if avg_slippage_bps is not None and avg_slippage_bps > 50.0:
        alerts.append(
            {
                "type": "high_slippage",
                "symbol": symbol,
                "metric": "avg_slippage_bps",
                "value": avg_slippage_bps,
                "threshold": 50.0,
                "message": f"Average slippage {avg_slippage_bps:.2f} bps exceeds threshold 50 bps",
            }
        )
    
    return alerts


async def monitor_tracking_error(
    asset: AssetSpec,
    campaign_id: str,
    tracking_error: dict[str, Any],
    *,
    threshold_pct: float = 0.05,
) -> list[dict[str, Any]]:
    """
    Monitor tracking error metrics and update Prometheus.
    
    Args:
        asset: Asset specification
        campaign_id: Campaign identifier
        tracking_error: Tracking error metrics dict
        threshold_pct: Deviation threshold for alerts (default: 5%)
        
    Returns:
        List of alerts if threshold exceeded
    """
    alerts = update_tracking_error_metrics(
        asset.symbol,
        campaign_id,
        tracking_error,
        threshold_pct=threshold_pct,
    )
    
    return alerts


