"""Advanced metrics including penalized Calmar, multi-metric reports, and bootstrap confidence intervals."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from app.core.logging import logger


@dataclass
class MetricsReport:
    """Multi-metric report with confidence intervals."""

    metrics: dict[str, float] = field(default_factory=dict)
    confidence_intervals: dict[str, dict[str, float]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add(self, name: str, value: float) -> None:
        """Add a metric."""
        self.metrics[name] = value

    def add_confidence_interval(self, name: str, p5: float, p50: float, p95: float) -> None:
        """Add confidence interval for a metric."""
        self.confidence_intervals[name] = {"p5": p5, "p50": p50, "p95": p95}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "metrics": self.metrics,
            "confidence_intervals": self.confidence_intervals,
            "metadata": self.metadata,
        }

    @classmethod
    def from_returns(
        cls,
        returns_per_period: list[float] | pd.Series,
        *,
        equity_curve: list[float] | None = None,
        initial_capital: float = 10000.0,
        total_days: int | None = None,
        bootstrap_trials: int = 5000,
        seed: int | None = None,
    ) -> MetricsReport:
        """
        Create metrics report from returns.

        Args:
            returns_per_period: Returns per period (daily/weekly/monthly)
            equity_curve: Optional equity curve for drawdown metrics
            initial_capital: Initial capital
            total_days: Total days in period
            bootstrap_trials: Number of bootstrap trials
            seed: Random seed for reproducibility

        Returns:
            MetricsReport
        """
        if isinstance(returns_per_period, list):
            returns = pd.Series(returns_per_period)
        else:
            returns = returns_per_period

        if len(returns) == 0:
            return cls()

        report = cls()

        # Basic metrics
        mean_return = float(returns.mean())
        std_return = float(returns.std(ddof=1))
        annualized_return = mean_return * 252 if len(returns) > 0 else 0.0
        annualized_vol = std_return * np.sqrt(252) if std_return > 0 else 0.0

        # CAGR
        if len(returns) > 0:
            total_return = (1 + returns).prod() - 1
            years = len(returns) / 252.0 if len(returns) < 252 else len(returns) / 252.0
            cagr = ((1 + total_return) ** (1 / years) - 1) * 100 if years > 0 and total_return > -1 else 0.0
        else:
            cagr = 0.0

        # Sharpe ratio
        sharpe = (annualized_return / annualized_vol) if annualized_vol > 0 else 0.0

        # Sortino ratio (downside deviation)
        downside_returns = returns[returns < 0]
        downside_std = float(downside_returns.std(ddof=1)) if len(downside_returns) > 1 else 0.0
        downside_vol = downside_std * np.sqrt(252) if downside_std > 0 else 0.0
        sortino = (annualized_return / downside_vol) if downside_vol > 0 else 0.0

        # Max drawdown
        if equity_curve and len(equity_curve) > 1:
            equity_series = pd.Series(equity_curve)
            running_max = equity_series.expanding().max()
            drawdown = (equity_series - running_max) / running_max
            max_drawdown = abs(float(drawdown.min())) * 100 if not drawdown.empty else 0.0

            # Longest drawdown period
            underwater = equity_series < running_max
            if underwater.any():
                groups = (underwater != underwater.shift()).cumsum()
                drawdown_periods = underwater.groupby(groups).cumsum()
                longest_drawdown_days = int(drawdown_periods.max()) if len(drawdown_periods) > 0 else 0
            else:
                longest_drawdown_days = 0

            # Average recovery days
            recovery_days = cls._calculate_avg_recovery_days(equity_series)

            # Ulcer index
            ulcer_index = cls._calculate_ulcer_index(equity_series)
        else:
            max_drawdown = 0.0
            longest_drawdown_days = 0
            recovery_days = 0.0
            ulcer_index = 0.0

        # Calmar ratio
        calmar = (cagr / max_drawdown) if max_drawdown > 0 else 0.0

        # MAR ratio (same as Calmar)
        mar_ratio = calmar

        # Calmar penalized by drawdown duration
        if total_days and total_days > 0:
            drawdown_penalty = longest_drawdown_days / total_days
            calmar_penalized = calmar * (1 - drawdown_penalty)
        else:
            calmar_penalized = calmar

        # Add metrics
        report.add("cagr", cagr)
        report.add("sharpe", sharpe)
        report.add("sortino", sortino)
        report.add("max_drawdown", max_drawdown)
        report.add("calmar", calmar)
        report.add("calmar_penalized", calmar_penalized)
        report.add("mar_ratio", mar_ratio)
        report.add("ulcer_index", ulcer_index)
        report.add("drawdown_recovery", recovery_days)
        report.add("longest_drawdown_days", float(longest_drawdown_days))

        # Bootstrap confidence intervals
        if bootstrap_trials > 0:
            ci_metrics = cls._bootstrap_confidence_intervals(
                returns,
                equity_curve=equity_curve,
                initial_capital=initial_capital,
                trials=bootstrap_trials,
                seed=seed,
            )
            for metric_name, ci_values in ci_metrics.items():
                report.add_confidence_interval(metric_name, ci_values["p5"], ci_values["p50"], ci_values["p95"])

        # Metadata
        report.metadata = {
            "n_periods": len(returns),
            "total_days": total_days,
            "bootstrap_trials": bootstrap_trials,
            "seed": seed,
        }

        return report

    @staticmethod
    def _calculate_avg_recovery_days(equity_series: pd.Series) -> float:
        """Calculate average recovery days from drawdowns."""
        if len(equity_series) < 2:
            return 0.0

        running_max = equity_series.expanding().max()
        underwater = equity_series < running_max

        if not underwater.any():
            return 0.0

        # Find recovery periods (transitions from underwater to above water)
        recovery_periods = []
        in_drawdown = False
        drawdown_start = None

        for i, is_underwater in enumerate(underwater):
            if is_underwater and not in_drawdown:
                in_drawdown = True
                drawdown_start = i
            elif not is_underwater and in_drawdown:
                in_drawdown = False
                if drawdown_start is not None:
                    recovery_days = i - drawdown_start
                    recovery_periods.append(recovery_days)
                drawdown_start = None

        return float(np.mean(recovery_periods)) if recovery_periods else 0.0

    @staticmethod
    def _calculate_ulcer_index(equity_series: pd.Series) -> float:
        """Calculate Ulcer Index."""
        if len(equity_series) < 2:
            return 0.0

        running_max = equity_series.expanding().max()
        drawdown_pct = ((equity_series - running_max) / running_max) * 100
        drawdown_squared = drawdown_pct ** 2
        ulcer_index = np.sqrt(drawdown_squared.mean())

        return float(ulcer_index)

    @staticmethod
    def _bootstrap_confidence_intervals(
        returns: pd.Series,
        *,
        equity_curve: list[float] | None = None,
        initial_capital: float = 10000.0,
        trials: int = 5000,
        seed: int | None = None,
    ) -> dict[str, dict[str, float]]:
        """
        Calculate bootstrap confidence intervals for key metrics.

        Args:
            returns: Returns series
            equity_curve: Optional equity curve
            initial_capital: Initial capital
            trials: Number of bootstrap trials
            seed: Random seed

        Returns:
            Dict with confidence intervals for each metric
        """
        rng = np.random.default_rng(seed)
        n = len(returns)

        if n < 10:
            return {}

        # Bootstrap samples
        cagr_samples = []
        sharpe_samples = []
        calmar_samples = []

        for _ in range(trials):
            # Resample with replacement
            sample_indices = rng.integers(0, n, size=n)
            sample_returns = returns.iloc[sample_indices]

            # Calculate metrics for this sample
            if len(sample_returns) > 0:
                total_return = (1 + sample_returns).prod() - 1
                years = n / 252.0
                cagr_sample = ((1 + total_return) ** (1 / years) - 1) * 100 if years > 0 and total_return > -1 else 0.0

                mean_ret = sample_returns.mean()
                std_ret = sample_returns.std(ddof=1)
                annual_ret = mean_ret * 252
                annual_vol = std_ret * np.sqrt(252) if std_ret > 0 else 0.0
                sharpe_sample = (annual_ret / annual_vol) if annual_vol > 0 else 0.0

                # Max drawdown from sample
                if equity_curve:
                    sample_equity = [initial_capital]
                    for ret in sample_returns:
                        sample_equity.append(sample_equity[-1] * (1 + ret))
                    equity_series = pd.Series(sample_equity)
                    running_max = equity_series.expanding().max()
                    drawdown = (equity_series - running_max) / running_max
                    max_dd = abs(drawdown.min()) * 100 if not drawdown.empty else 0.0
                else:
                    max_dd = abs(sample_returns.min()) * 100

                calmar_sample = (cagr_sample / max_dd) if max_dd > 0 else 0.0

                cagr_samples.append(cagr_sample)
                sharpe_samples.append(sharpe_sample)
                calmar_samples.append(calmar_sample)

        # Calculate percentiles
        results = {}
        if cagr_samples:
            results["cagr"] = {
                "p5": float(np.percentile(cagr_samples, 5)),
                "p50": float(np.percentile(cagr_samples, 50)),
                "p95": float(np.percentile(cagr_samples, 95)),
            }
        if sharpe_samples:
            results["sharpe"] = {
                "p5": float(np.percentile(sharpe_samples, 5)),
                "p50": float(np.percentile(sharpe_samples, 50)),
                "p95": float(np.percentile(sharpe_samples, 95)),
            }
        if calmar_samples:
            results["calmar"] = {
                "p5": float(np.percentile(calmar_samples, 5)),
                "p50": float(np.percentile(calmar_samples, 50)),
                "p95": float(np.percentile(calmar_samples, 95)),
            }

        return results


def calmar_penalized(
    calmar: float,
    longest_drawdown_days: int,
    total_days: int,
) -> float:
    """
    Calculate penalized Calmar ratio.

    Args:
        calmar: Base Calmar ratio
        longest_drawdown_days: Longest drawdown period in days
        total_days: Total period in days

    Returns:
        Penalized Calmar ratio
    """
    if total_days <= 0:
        return calmar

    penalty = longest_drawdown_days / total_days
    return calmar * (1 - penalty)





