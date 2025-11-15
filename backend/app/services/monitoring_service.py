"""Continuous performance monitoring service with alerts."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from app.backtesting.engine import BacktestEngine
from app.backtesting.metrics import calculate_metrics
from app.backtesting.unified_risk_manager import UnifiedRiskManager
from app.core.database import SessionLocal
from app.core.logging import logger
from app.data.curation import DataCuration
from app.data.universe import AssetSpec
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
            logger.debug(f"Failed to monitor performance for {asset.symbol}", extra={"error": str(exc)})

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
            logger.debug(f"Failed to monitor regime health for {asset.symbol}", extra={"error": str(exc)})

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
            
            return {
                "status": "ok",
                "asset": self.asset,
                "venue": self.venue,
                "trades_count": len(trades),
                "risk_status": risk_status,
                "alerts": alerts,
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as exc:
            logger.exception("Failed to update monitoring metrics", extra={"asset": self.asset, "error": str(exc)})
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
            logger.warning("Failed to update risk metrics", extra={"asset": self.asset, "error": str(exc)})
            return {"status": "error", "error": str(exc)}


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
