"""Performance monitoring metrics for Prometheus dashboards."""
from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
from prometheus_client import Gauge

from app.backtesting.metrics import calculate_metrics
from app.core.logging import logger
from app.data.curation import DataCuration
from app.quant.regime import RegimeClassifier

ROLLING_SHARPE = Gauge(
    "strategy_rolling_sharpe",
    "Rolling Sharpe ratio by asset and horizon",
    ["asset", "venue", "horizon"],
)

HIT_RATE = Gauge(
    "strategy_hit_rate",
    "Rolling hit rate (winning trades / total trades) by asset and horizon",
    ["asset", "venue", "horizon"],
)

EQUITY_SLOPE = Gauge(
    "strategy_equity_slope",
    "Equity curve slope (basis points per day) by asset",
    ["asset", "venue"],
)

REGIME_PROBABILITY = Gauge(
    "strategy_regime_probability",
    "Current regime probability by asset and regime type",
    ["asset", "venue", "regime"],
)

REGIME_DRIFT = Gauge(
    "strategy_regime_drift",
    "Regime probability drift from historical mean by asset and regime",
    ["asset", "venue", "regime"],
)

STRESS_ALERT_COUNT = Gauge(
    "strategy_stress_alert_count",
    "Consecutive sessions with stress probability above threshold by asset",
    ["asset", "venue"],
)

MAX_DRAWDOWN = Gauge(
    "strategy_max_drawdown",
    "Maximum drawdown by asset and horizon",
    ["asset", "venue", "horizon"],
)

PROFIT_FACTOR = Gauge(
    "strategy_profit_factor",
    "Profit factor (gross profit / gross loss) by asset and horizon",
    ["asset", "venue", "horizon"],
)


class PerformanceMonitor:
    """Monitor and expose performance metrics via Prometheus."""

    def __init__(
        self,
        asset: str = "BTCUSDT",
        venue: str = "binance",
        *,
        lookback_days: int = 365 * 5,
        regime_classifier: RegimeClassifier | None = None,
    ) -> None:
        """
        Initialize performance monitor.
        
        Args:
            asset: Asset symbol to monitor
            venue: Trading venue
            lookback_days: Historical lookback for metrics
            regime_classifier: Optional regime classifier for health checks
        """
        self.asset = asset
        self.venue = venue
        self.lookback_days = lookback_days
        self.regime_classifier = regime_classifier
        self.curation = DataCuration()
        self.regime_history: deque[dict[str, float]] = deque(maxlen=100)
        self.stress_alert_sessions: int = 0

    def update_rolling_metrics(
        self,
        trades: list[dict[str, Any]],
        equity_curve: list[float],
        *,
        horizons: list[int] = [7, 30, 90],
    ) -> None:
        """
        Update rolling Sharpe, hit rate, and equity slope metrics.
        
        Args:
            trades: List of trade dictionaries
            equity_curve: Equity curve values
            horizons: List of rolling window sizes in days
        """
        if not trades or len(equity_curve) < 2:
            logger.warning("Insufficient data for rolling metrics", extra={"asset": self.asset, "trades": len(trades)})
            return
        
        df_trades = pd.DataFrame(trades)
        if "exit_time" not in df_trades.columns or "return_pct" not in df_trades.columns:
            logger.warning("Missing required columns in trades", extra={"asset": self.asset})
            return
        
        df_trades["exit_time"] = pd.to_datetime(df_trades["exit_time"])
        df_trades = df_trades.sort_values("exit_time")
        
        now = datetime.utcnow()
        
        for horizon in horizons:
            cutoff = now - timedelta(days=horizon)
            recent_trades = df_trades[df_trades["exit_time"] >= cutoff].copy()
            
            if len(recent_trades) < 5:
                continue
            
            returns = recent_trades["return_pct"].values
            
            sharpe = 0.0
            if len(returns) > 1 and np.std(returns) > 0:
                mean_return = np.mean(returns)
                std_return = np.std(returns)
                sharpe = (mean_return / std_return) * np.sqrt(252)
            
            hit_rate = (recent_trades["pnl"] > 0).sum() / len(recent_trades) * 100.0
            
            ROLLING_SHARPE.labels(asset=self.asset, venue=self.venue, horizon=f"{horizon}d").set(sharpe)
            HIT_RATE.labels(asset=self.asset, venue=self.venue, horizon=f"{horizon}d").set(hit_rate)
            
            max_dd = 0.0
            if recent_trades["pnl"].notna().any():
                recent_equity = equity_curve[-len(recent_trades):] if len(equity_curve) >= len(recent_trades) else equity_curve
                if len(recent_equity) > 1:
                    equity_series = pd.Series(recent_equity)
                    running_max = equity_series.expanding().max()
                    drawdown = ((equity_series - running_max) / running_max) * 100
                    max_dd = abs(drawdown.min()) if not drawdown.empty else 0.0
            
            MAX_DRAWDOWN.labels(asset=self.asset, venue=self.venue, horizon=f"{horizon}d").set(max_dd)
            
            profit_factor = 0.0
            gross_profit = recent_trades[recent_trades["pnl"] > 0]["pnl"].sum()
            gross_loss = abs(recent_trades[recent_trades["pnl"] < 0]["pnl"].sum())
            if gross_loss > 0:
                profit_factor = gross_profit / gross_loss
            
            PROFIT_FACTOR.labels(asset=self.asset, venue=self.venue, horizon=f"{horizon}d").set(profit_factor)
        
        equity_slope = self._calculate_equity_slope(equity_curve)
        EQUITY_SLOPE.labels(asset=self.asset, venue=self.venue).set(equity_slope)

    def _calculate_equity_slope(self, equity_curve: list[float]) -> float:
        """Calculate equity curve slope in basis points per day."""
        if len(equity_curve) < 30:
            return 0.0
        
        recent_equity = equity_curve[-30:]
        equity_series = pd.Series(recent_equity)
        
        x = np.arange(len(equity_series))
        coeffs = np.polyfit(x, equity_series.values, 1)
        slope = coeffs[0]
        
        if len(equity_curve) > 0:
            slope_bps_per_day = (slope / equity_curve[-1]) * 10000 if equity_curve[-1] > 0 else 0.0
        else:
            slope_bps_per_day = 0.0
        
        return float(slope_bps_per_day)

    def update_regime_health(
        self,
        price_data: pd.DataFrame,
        *,
        stress_threshold: float = 0.6,
        alert_sessions: int = 3,
    ) -> dict[str, Any]:
        """
        Update regime health metrics and check for stress alerts.
        
        Args:
            price_data: DataFrame with OHLCV data
            stress_threshold: Probability threshold for stress regime alert (default: 0.6)
            alert_sessions: Number of consecutive sessions above threshold to trigger alert (default: 3)
            
        Returns:
            Dict with regime probabilities and alert status
        """
        if self.regime_classifier is None:
            return {"status": "no_classifier", "regime_probabilities": {}}
        
        try:
            regime_proba = self.regime_classifier.fit_predict_proba(price_data)
            if regime_proba.empty:
                return {"status": "empty_proba", "regime_probabilities": {}}
            
            current_proba = regime_proba.iloc[-1].to_dict()
            self.regime_history.append(current_proba.copy())
            
            for regime, proba in current_proba.items():
                REGIME_PROBABILITY.labels(asset=self.asset, venue=self.venue, regime=regime).set(float(proba))
                
                if len(self.regime_history) > 10:
                    historical_mean = np.mean([h.get(regime, 0.0) for h in self.regime_history])
                    drift = float(proba - historical_mean)
                    REGIME_DRIFT.labels(asset=self.asset, venue=self.venue, regime=regime).set(drift)
            
            stress_prob = current_proba.get("stress", 0.0)
            
            if stress_prob > stress_threshold:
                self.stress_alert_sessions += 1
            else:
                self.stress_alert_sessions = 0
            
            STRESS_ALERT_COUNT.labels(asset=self.asset, venue=self.venue).set(float(self.stress_alert_sessions))
            
            alert_triggered = self.stress_alert_sessions >= alert_sessions
            
            return {
                "status": "ok",
                "regime_probabilities": current_proba,
                "stress_probability": float(stress_prob),
                "stress_alert_sessions": self.stress_alert_sessions,
                "alert_triggered": alert_triggered,
            }
        except Exception as exc:
            logger.warning("Failed to update regime health", extra={"asset": self.asset, "error": str(exc)})
            return {"status": "error", "error": str(exc)}

    def check_threshold_alerts(
        self,
        thresholds: dict[str, float],
    ) -> list[dict[str, Any]]:
        """
        Check if metrics have fallen below thresholds.
        
        Args:
            thresholds: Dict of metric names to threshold values, e.g.:
                {"rolling_sharpe_30d": 0.5, "hit_rate_30d": 40.0, "equity_slope": -10.0}
                
        Returns:
            List of alert dicts for metrics below thresholds
        """
        alerts = []
        
        for metric_name, threshold in thresholds.items():
            if "sharpe" in metric_name.lower():
                horizon = metric_name.split("_")[-1] if "_" in metric_name else "30d"
                current_value = ROLLING_SHARPE.labels(asset=self.asset, venue=self.venue, horizon=horizon)._value.get()
                if current_value is not None and current_value < threshold:
                    alerts.append({
                        "metric": metric_name,
                        "current_value": float(current_value),
                        "threshold": threshold,
                        "asset": self.asset,
                        "severity": "warning" if current_value > threshold * 0.8 else "critical",
                    })
            elif "hit_rate" in metric_name.lower():
                horizon = metric_name.split("_")[-1] if "_" in metric_name else "30d"
                current_value = HIT_RATE.labels(asset=self.asset, venue=self.venue, horizon=horizon)._value.get()
                if current_value is not None and current_value < threshold:
                    alerts.append({
                        "metric": metric_name,
                        "current_value": float(current_value),
                        "threshold": threshold,
                        "asset": self.asset,
                        "severity": "warning" if current_value > threshold * 0.8 else "critical",
                    })
            elif "equity_slope" in metric_name.lower():
                current_value = EQUITY_SLOPE.labels(asset=self.asset, venue=self.venue)._value.get()
                if current_value is not None and current_value < threshold:
                    alerts.append({
                        "metric": metric_name,
                        "current_value": float(current_value),
                        "threshold": threshold,
                        "asset": self.asset,
                        "severity": "warning" if current_value > threshold * 0.5 else "critical",
                    })
        
        return alerts


def update_performance_metrics(
    asset: str = "BTCUSDT",
    venue: str = "binance",
    *,
    trades: list[dict[str, Any]] | None = None,
    equity_curve: list[float] | None = None,
    price_data: pd.DataFrame | None = None,
    regime_classifier: RegimeClassifier | None = None,
) -> dict[str, Any]:
    """
    Convenience function to update all performance metrics at once.
    
    Args:
        asset: Asset symbol
        venue: Trading venue
        trades: List of trades (optional, will fetch from backtest if None)
        equity_curve: Equity curve (optional, will fetch from backtest if None)
        price_data: Price data for regime classification (optional)
        regime_classifier: Optional regime classifier
        
    Returns:
        Dict with update status and metrics
    """
    monitor = PerformanceMonitor(asset=asset, venue=venue, regime_classifier=regime_classifier)
    
    if trades is None or equity_curve is None:
        try:
            from app.backtesting.engine import BacktestEngine
            from datetime import datetime, timedelta
            engine = BacktestEngine()
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=365 * 2)
            result = engine.run_backtest(start_date, end_date)
            if "error" not in result:
                trades = result.get("trades", [])
                equity_curve = result.get("equity_curve", [])
            else:
                return {"status": "error", "error": result.get("error")}
        except Exception as exc:
            logger.warning("Failed to fetch backtest data", extra={"error": str(exc)})
            return {"status": "error", "error": str(exc)}
    
    if trades and equity_curve:
        monitor.update_rolling_metrics(trades, equity_curve)
    
    regime_status = {}
    if price_data is not None:
        regime_status = monitor.update_regime_health(price_data)
    
    return {
        "status": "ok",
        "asset": asset,
        "venue": venue,
        "regime_status": regime_status,
    }




