"""Tracking error calculation between theoretical and realistic equity curves."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class TrackingErrorMetrics:
    """Metrics for tracking error between theoretical and realistic equity curves."""

    mean_deviation: float  # Mean tracking error
    max_divergence: float  # Maximum absolute divergence
    tracking_sharpe: float  # Sharpe ratio of tracking error
    rmse: float  # Root Mean Squared Error
    correlation: float  # Correlation between curves
    max_drawdown_divergence: float  # Max drawdown difference
    cumulative_tracking_error: float  # Cumulative difference at end
    p95_divergence: float  # 95th percentile divergence
    p99_divergence: float  # 99th percentile divergence


def calculate_tracking_error(
    theoretical_equity: list[float] | np.ndarray,
    realistic_equity: list[float] | np.ndarray,
) -> dict[str, Any]:
    """
    Calculate tracking error metrics between theoretical and realistic equity curves.
    
    Args:
        theoretical_equity: Equity curve without frictions (ideal execution)
        realistic_equity: Equity curve with frictions (real execution)
        
    Returns:
        Dict with tracking error metrics
    """
    theoretical = np.array(theoretical_equity)
    realistic = np.array(realistic_equity)
    
    # Ensure same length
    min_len = min(len(theoretical), len(realistic))
    theoretical = theoretical[:min_len]
    realistic = realistic[:min_len]
    
    if len(theoretical) == 0 or len(realistic) == 0:
        return {
            "tracking_error": np.array([]),
            "mean_deviation": 0.0,
            "max_divergence": 0.0,
            "tracking_sharpe": 0.0,
            "rmse": 0.0,
            "correlation": 0.0,
            "max_drawdown_divergence": 0.0,
            "cumulative_tracking_error": 0.0,
            "p95_divergence": 0.0,
            "p99_divergence": 0.0,
        }
    
    # Calculate tracking error (realistic - theoretical)
    tracking_error = realistic - theoretical
    
    # Mean deviation
    mean_deviation = float(np.mean(tracking_error))
    
    # Max divergence (absolute)
    max_divergence = float(np.max(np.abs(tracking_error)))
    
    # Root Mean Squared Error
    rmse = float(np.sqrt(np.mean(tracking_error**2)))
    
    # Correlation
    if len(theoretical) > 1 and np.std(theoretical) > 0 and np.std(realistic) > 0:
        correlation = float(np.corrcoef(theoretical, realistic)[0, 1])
    else:
        correlation = 1.0 if len(theoretical) == 1 else 0.0
    
    # Tracking Sharpe (Sharpe ratio of tracking error)
    if len(tracking_error) > 1 and np.std(tracking_error) > 0:
        # Annualize assuming 252 trading days
        tracking_sharpe = float((np.mean(tracking_error) / np.std(tracking_error)) * np.sqrt(252))
    else:
        tracking_sharpe = 0.0
    
    # Cumulative tracking error at end
    cumulative_tracking_error = float(tracking_error[-1])
    
    # Percentiles of absolute divergence
    abs_divergence = np.abs(tracking_error)
    p95_divergence = float(np.percentile(abs_divergence, 95))
    p99_divergence = float(np.percentile(abs_divergence, 99))
    
    # Max drawdown divergence
    # Calculate drawdowns for both curves
    def calculate_max_drawdown(curve: np.ndarray) -> float:
        running_max = np.maximum.accumulate(curve)
        drawdown = (curve - running_max) / running_max * 100
        return float(np.abs(np.min(drawdown))) if len(drawdown) > 0 else 0.0
    
    theoretical_dd = calculate_max_drawdown(theoretical)
    realistic_dd = calculate_max_drawdown(realistic)
    max_drawdown_divergence = realistic_dd - theoretical_dd
    
    return {
        "tracking_error": tracking_error.tolist(),
        "mean_deviation": round(mean_deviation, 4),
        "max_divergence": round(max_divergence, 4),
        "tracking_sharpe": round(tracking_sharpe, 4),
        "rmse": round(rmse, 4),
        "correlation": round(correlation, 4),
        "max_drawdown_divergence": round(max_drawdown_divergence, 4),
        "cumulative_tracking_error": round(cumulative_tracking_error, 4),
        "p95_divergence": round(p95_divergence, 4),
        "p99_divergence": round(p99_divergence, 4),
        "theoretical_max_drawdown": round(theoretical_dd, 4),
        "realistic_max_drawdown": round(realistic_dd, 4),
    }


def calculate_tracking_error_metrics(
    theoretical_equity: list[float] | np.ndarray,
    realistic_equity: list[float] | np.ndarray,
) -> TrackingErrorMetrics:
    """
    Calculate TrackingErrorMetrics object from equity curves.
    
    Args:
        theoretical_equity: Equity curve without frictions
        realistic_equity: Equity curve with frictions
        
    Returns:
        TrackingErrorMetrics object
    """
    results = calculate_tracking_error(theoretical_equity, realistic_equity)
    
    return TrackingErrorMetrics(
        mean_deviation=results["mean_deviation"],
        max_divergence=results["max_divergence"],
        tracking_sharpe=results["tracking_sharpe"],
        rmse=results["rmse"],
        correlation=results["correlation"],
        max_drawdown_divergence=results["max_drawdown_divergence"],
        cumulative_tracking_error=results["cumulative_tracking_error"],
        p95_divergence=results["p95_divergence"],
        p99_divergence=results["p99_divergence"],
    )


def calculate_period_tracking_error(
    theoretical_equity: list[float] | np.ndarray,
    realistic_equity: list[float] | np.ndarray,
    periods: list[tuple[int, int]] | None = None,
) -> dict[str, dict[str, float]]:
    """
    Calculate tracking error for specific periods.
    
    Args:
        theoretical_equity: Theoretical equity curve
        realistic_equity: Realistic equity curve
        periods: List of (start_idx, end_idx) tuples for periods to analyze
        
    Returns:
        Dict mapping period names to tracking error metrics
    """
    theoretical = np.array(theoretical_equity)
    realistic = np.array(realistic_equity)
    
    if periods is None:
        # Default: analyze by quarters
        total_len = min(len(theoretical), len(realistic))
        quarter_len = total_len // 4
        periods = [
            (0, quarter_len),
            (quarter_len, 2 * quarter_len),
            (2 * quarter_len, 3 * quarter_len),
            (3 * quarter_len, total_len),
        ]
    
    period_metrics = {}
    
    for idx, (start, end) in enumerate(periods):
        if start >= len(theoretical) or start >= len(realistic):
            continue
        
        end = min(end, len(theoretical), len(realistic))
        if start >= end:
            continue
        
        period_theoretical = theoretical[start:end]
        period_realistic = realistic[start:end]
        
        period_results = calculate_tracking_error(period_theoretical, period_realistic)
        period_metrics[f"period_{idx + 1}"] = {
            k: v for k, v in period_results.items() if k != "tracking_error"
        }
    
    return period_metrics


