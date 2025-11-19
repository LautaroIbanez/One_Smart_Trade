"""Performance monitoring and automatic recalibration triggers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from app.core.logging import logger
from app.quant.regime import RegimeClassifier


@dataclass(frozen=True, slots=True)
class RecalibrationEvent:
    """Event triggering recalibration job."""

    asset: str
    venue: str
    regime_snapshot: dict[str, float]
    current_metrics: dict[str, float]
    baseline_metrics: dict[str, float]
    trigger_reason: str
    trigger_pct: float
    timestamp: datetime


class PerformanceMonitor:
    """Monitor rolling performance metrics and detect significant changes."""

    def __init__(
        self,
        window_days: int = 30,
        trigger_pct: float = 0.15,
    ) -> None:
        """
        Initialize performance monitor.
        
        Args:
            window_days: Rolling window size in days for metric calculation
            trigger_pct: Percentage change threshold to trigger recalibration (default: 15%)
        """
        self.window_days = window_days
        self.trigger_pct = trigger_pct

    def calculate_rolling_metrics(
        self,
        trades: pd.DataFrame,
        *,
        window_days: int | None = None,
    ) -> dict[str, float]:
        """
        Calculate rolling Sharpe and volatility metrics.
        
        Args:
            trades: DataFrame with columns ['exit_time', 'return_pct', 'pnl']
            window_days: Override default window size
            
        Returns:
            Dict with rolling_sharpe_30d, rolling_volatility_30d, etc.
        """
        window = window_days or self.window_days
        
        if trades.empty:
            return {
                f"rolling_sharpe_{window}d": 0.0,
                f"rolling_volatility_{window}d": 0.0,
            }
        
        df = trades.copy()
        if "exit_time" not in df.columns:
            df["exit_time"] = pd.to_datetime(df.index)
        else:
            df["exit_time"] = pd.to_datetime(df["exit_time"])
        
        df = df.sort_values("exit_time")
        df["days_ago"] = (df["exit_time"].max() - df["exit_time"]).dt.days
        
        recent_trades = df[df["days_ago"] <= window]
        
        if len(recent_trades) < 10:
            return {
                f"rolling_sharpe_{window}d": 0.0,
                f"rolling_volatility_{window}d": 0.0,
            }
        
        returns = recent_trades["return_pct"].values
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        
        rolling_sharpe = (mean_return / std_return * np.sqrt(252)) if std_return > 0 else 0.0
        rolling_volatility = std_return * np.sqrt(252)
        
        return {
            f"rolling_sharpe_{window}d": float(rolling_sharpe),
            f"rolling_volatility_{window}d": float(rolling_volatility),
            "trade_count": len(recent_trades),
        }

    def check_trigger(
        self,
        current_metrics: dict[str, float],
        baseline_metrics: dict[str, float],
        *,
        metric_name: str = "rolling_sharpe_30d",
    ) -> bool:
        """
        Check if metric change exceeds trigger threshold.
        
        Args:
            current_metrics: Current rolling metrics
            baseline_metrics: Baseline metrics for comparison
            metric_name: Metric to check (default: rolling_sharpe_30d)
            
        Returns:
            True if trigger threshold exceeded
        """
        current_value = current_metrics.get(metric_name, 0.0)
        baseline_value = baseline_metrics.get(metric_name, 0.0)
        
        if baseline_value == 0:
            return abs(current_value) > 0.01
        
        change_pct = abs((current_value - baseline_value) / baseline_value)
        return change_pct > self.trigger_pct

    def detect_recalibration_triggers(
        self,
        trades: pd.DataFrame,
        baseline_metrics: dict[str, float],
        asset: str = "BTCUSDT",
        venue: str = "binance",
        *,
        regime_classifier: RegimeClassifier | None = None,
        price_data: pd.DataFrame | None = None,
    ) -> RecalibrationEvent | None:
        """
        Detect if recalibration is needed based on metric changes.
        
        Args:
            trades: DataFrame with trade returns
            baseline_metrics: Baseline metrics for comparison
            asset: Asset symbol
            venue: Trading venue
            regime_classifier: Optional regime classifier for snapshot
            price_data: Optional price data for regime classification
            
        Returns:
            RecalibrationEvent if trigger detected, None otherwise
        """
        current_metrics = self.calculate_rolling_metrics(trades)
        
        trigger_detected = False
        trigger_reason = ""
        
        for metric_name in ["rolling_sharpe_30d", "rolling_volatility_30d"]:
            if self.check_trigger(current_metrics, baseline_metrics, metric_name=metric_name):
                trigger_detected = True
                current_val = current_metrics.get(metric_name, 0.0)
                baseline_val = baseline_metrics.get(metric_name, 0.0)
                change_pct = abs((current_val - baseline_val) / baseline_val) if baseline_val != 0 else 0.0
                trigger_reason = f"{metric_name} changed by {change_pct * 100:.1f}%"
                break
        
        if not trigger_detected:
            return None
        
        regime_snapshot = {}
        if regime_classifier and price_data is not None:
            try:
                regime_proba = regime_classifier.fit_predict_proba(price_data)
                if not regime_proba.empty:
                    regime_snapshot = regime_proba.iloc[-1].to_dict()
            except Exception as exc:
                logger.warning("Failed to generate regime snapshot", extra={"error": str(exc)})
        
        return RecalibrationEvent(
            asset=asset,
            venue=venue,
            regime_snapshot=regime_snapshot,
            current_metrics=current_metrics,
            baseline_metrics=baseline_metrics,
            trigger_reason=trigger_reason,
            trigger_pct=self.trigger_pct,
            timestamp=datetime.utcnow(),
        )


def statistical_significance_test(
    candidate_metrics: dict[str, float],
    baseline_metrics: dict[str, float],
    *,
    alpha: float = 0.05,
    min_samples: int = 30,
) -> tuple[bool, float, str]:
    """
    Test if candidate improvement is statistically significant.
    
    Uses t-test on Sharpe ratios or other metrics.
    
    Args:
        candidate_metrics: Metrics from candidate strategy
        baseline_metrics: Metrics from baseline/champion
        alpha: Significance level (default: 0.05)
        min_samples: Minimum samples required for test
        
    Returns:
        Tuple of (is_significant, p_value, reason)
    """
    candidate_sharpe = candidate_metrics.get("sharpe", 0.0)
    baseline_sharpe = baseline_metrics.get("sharpe", 0.0)
    
    if candidate_sharpe <= baseline_sharpe:
        return False, 1.0, "Candidate Sharpe not greater than baseline"
    
    candidate_trades = candidate_metrics.get("total_trades", 0)
    baseline_trades = baseline_metrics.get("total_trades", 0)
    
    if candidate_trades < min_samples or baseline_trades < min_samples:
        return False, 1.0, f"Insufficient samples (candidate={candidate_trades}, baseline={baseline_trades})"
    
    improvement = candidate_sharpe - baseline_sharpe
    improvement_pct = (improvement / abs(baseline_sharpe)) * 100 if baseline_sharpe != 0 else 0.0
    
    if improvement_pct < 5.0:
        return False, 1.0, f"Improvement too small ({improvement_pct:.1f}%)"
    
    candidate_std = candidate_metrics.get("max_drawdown", 0.0) / 3.0
    baseline_std = baseline_metrics.get("max_drawdown", 0.0) / 3.0
    
    if candidate_std == 0 or baseline_std == 0:
        return improvement_pct > 10.0, 0.05 if improvement_pct > 10.0 else 0.5, "Cannot compute significance, using heuristic"
    
    pooled_std = np.sqrt((candidate_std**2 + baseline_std**2) / 2)
    se = pooled_std * np.sqrt(1 / candidate_trades + 1 / baseline_trades)
    
    if se == 0:
        return False, 1.0, "Standard error is zero"
    
    t_stat = improvement / se
    df = candidate_trades + baseline_trades - 2
    p_value = 1.0 - stats.t.cdf(abs(t_stat), df)
    
    is_significant = p_value < alpha
    
    reason = f"t={t_stat:.2f}, p={p_value:.4f}, improvement={improvement_pct:.1f}%"
    
    return is_significant, p_value, reason





