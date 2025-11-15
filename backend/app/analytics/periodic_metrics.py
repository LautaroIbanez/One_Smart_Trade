from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd


@dataclass
class PeriodicMetrics:
    horizon: Literal["monthly", "quarterly"]
    stats: dict[str, float]
    distribution: pd.Series


class PeriodicMetricsBuilder:
    def build(self, equity_curve: pd.Series) -> list[PeriodicMetrics]:
        returns = equity_curve.pct_change().dropna()
        monthly = (1 + returns).resample("M").prod() - 1
        quarterly = (1 + returns).resample("Q").prod() - 1
        return [self._describe("monthly", monthly), self._describe("quarterly", quarterly)]

    @staticmethod
    def validate_inputs(
        equity_curve: pd.Series,
        *,
        max_gap_days: int = 5,
        min_months: int = 12,
    ) -> dict[str, float | int | bool]:
        """
        Validate historical data before resampling:
        - Detect large gaps (> max_gap_days)
        - Ensure minimum length (months)
        - Report coverage ratio vs continuous date range
        """
        if equity_curve.empty:
            return {"ok": False, "reason": "empty_series", "coverage_pct": 0.0, "max_gap_days": 0, "months": 0}
        s = equity_curve.dropna()
        idx = pd.to_datetime(s.index)
        if len(idx) < 2:
            return {"ok": False, "reason": "insufficient_points", "coverage_pct": 0.0, "max_gap_days": 0, "months": 0}
        # Gaps
        diffs = idx.to_series().diff().dt.days.fillna(0).astype(int)
        max_gap = int(diffs.max())
        # Coverage vs continuous
        full_range = pd.date_range(start=idx.min(), end=idx.max(), freq="D")
        coverage = len(idx.normalize().unique()) / max(len(full_range), 1)
        # Months of data
        months = max(1, ((idx.max().year - idx.min().year) * 12 + (idx.max().month - idx.min().month)))
        ok = (max_gap <= max_gap_days) and (months >= min_months)
        return {
            "ok": bool(ok),
            "reason": "" if ok else ("large_gaps" if max_gap > max_gap_days else "insufficient_months"),
            "coverage_pct": float(round(coverage, 4)),
            "max_gap_days": max_gap,
            "months": months,
        }

    def _describe(self, horizon: str, series: pd.Series) -> PeriodicMetrics:
        desc = {
            "mean": float(series.mean()),
            "std": float(series.std(ddof=1)),
            "p25": float(series.quantile(0.25)),
            "p75": float(series.quantile(0.75)),
            "skew": float(series.skew()),
            "kurtosis": float(series.kurtosis()),
            "negative_pct": float((series < 0).mean()),
            "max_loss_streak": int(self._max_loss_streak(series)),
            "max_loss_duration": int(self._max_loss_duration(series)),
        }
        return PeriodicMetrics(horizon=horizon, stats=desc, distribution=series)

    def _max_loss_streak(self, series: pd.Series) -> int:
        if series.empty:
            return 0
        # Count consecutive negative periods
        losses = (series < 0).astype(int)
        groups = (losses != losses.shift()).cumsum()
        streaks = losses.groupby(groups).cumsum()
        return int(streaks.max() or 0)

    def _max_loss_duration(self, series: pd.Series) -> int:
        if series.empty:
            return 0
        # Duration in months/quarters underwater relative to prior peak
        equity = (1 + series).cumprod()
        underwater = equity < equity.cummax()
        groups = (underwater != underwater.shift()).cumsum()
        durations = underwater.groupby(groups).cumsum()
        return int(durations.max() or 0)


