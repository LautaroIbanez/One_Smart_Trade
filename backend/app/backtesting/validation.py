"""Pre-execution validations for backtest campaigns."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.core.logging import logger


class CampaignAbort(Exception):
    """Exception raised when campaign validation fails."""

    def __init__(self, reason: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.details = details or {}


@dataclass
class ValidationResult:
    """Result of campaign validation."""

    valid: bool
    reason: str | None = None
    details: dict[str, Any] | None = None

    def raise_if_invalid(self) -> None:
        """Raise CampaignAbort if validation failed."""
        if not self.valid:
            raise CampaignAbort(self.reason or "Validation failed", self.details)


class CampaignValidator:
    """Validates backtest campaigns before execution."""

    def __init__(
        self,
        *,
        min_days: int = 730,
        min_monthly_coverage: float = 0.90,
        max_gap_days: int = 1,
        min_trades: int = 50,
        min_months: int = 24,
    ) -> None:
        """
        Initialize validator.

        Args:
            min_days: Minimum window duration in days (default: 730 = 2 years)
            min_monthly_coverage: Minimum monthly data coverage (default: 90%)
            max_gap_days: Maximum consecutive gap in days (default: 1)
            min_trades: Minimum number of trades required (default: 50)
            min_months: Minimum months of history required (default: 24)
        """
        self.min_days = min_days
        self.min_monthly_coverage = min_monthly_coverage
        self.max_gap_days = max_gap_days
        self.min_trades = min_trades
        self.min_months = min_months

    def validate_window(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> ValidationResult:
        """
        Validate time window.

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            ValidationResult
        """
        duration_days = (end_date - start_date).days

        if duration_days < self.min_days:
            return ValidationResult(
                valid=False,
                reason="Window too short",
                details={
                    "duration_days": duration_days,
                    "min_days": self.min_days,
                    "missing_days": self.min_days - duration_days,
                },
            )

        return ValidationResult(valid=True, details={"duration_days": duration_days})

    def validate_data_coverage(
        self,
        candle_series: pd.DataFrame,
        timeframe: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> ValidationResult:
        """
        Validate data coverage and gaps.

        Args:
            candle_series: DataFrame with timestamp index
            timeframe: Timeframe string (e.g., "1h", "4h", "1d")
            start_date: Expected start date
            end_date: Expected end date

        Returns:
            ValidationResult
        """
        # Calculate expected bars per month based on timeframe
        timeframe_to_hours = {
            "15m": 0.25,
            "30m": 0.5,
            "1h": 1.0,
            "4h": 4.0,
            "1d": 24.0,
            "1w": 168.0,
        }
        hours_per_bar = timeframe_to_hours.get(timeframe, 1.0)
        bars_per_day = 24.0 / hours_per_bar

        # Check monthly coverage
        months = []
        current = start_date.replace(day=1)
        while current <= end_date:
            month_end = (current + pd.DateOffset(months=1)) - pd.Timedelta(days=1)
            month_end = min(month_end, end_date)

            month_data = candle_series[
                (candle_series.index >= current) & (candle_series.index <= month_end)
            ]

            expected_bars = (month_end - current).days * bars_per_day
            actual_bars = len(month_data)
            coverage = actual_bars / expected_bars if expected_bars > 0 else 0.0

            months.append(
                {
                    "month": current.strftime("%Y-%m"),
                    "expected_bars": expected_bars,
                    "actual_bars": actual_bars,
                    "coverage": coverage,
                }
            )

            current = current + pd.DateOffset(months=1)

        # Calculate overall coverage
        avg_coverage = sum(m["coverage"] for m in months) / len(months) if months else 0.0
        min_coverage = min(m["coverage"] for m in months) if months else 0.0

        if avg_coverage < self.min_monthly_coverage:
            return ValidationResult(
                valid=False,
                reason="Insufficient data density",
                details={
                    "avg_coverage": avg_coverage,
                    "min_coverage": min_coverage,
                    "required_coverage": self.min_monthly_coverage,
                    "monthly_details": months,
                },
            )

        # Check for gaps > max_gap_days
        if len(candle_series) > 1:
            timestamps = pd.to_datetime(candle_series.index)
            gaps = timestamps.to_series().diff()
            max_gap = gaps.max()

            # Convert gap to days
            max_gap_days = max_gap.total_seconds() / (24 * 3600) if pd.notna(max_gap) else 0.0

            if max_gap_days > self.max_gap_days:
                return ValidationResult(
                    valid=False,
                    reason="Dataset has gaps > 1 day consecutive",
                    details={
                        "max_gap_days": max_gap_days,
                        "max_allowed_gap_days": self.max_gap_days,
                    },
                )

        return ValidationResult(
            valid=True,
            details={
                "avg_coverage": avg_coverage,
                "min_coverage": min_coverage,
                "monthly_details": months,
            },
        )

    def validate_all(
        self,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
        candle_series: pd.DataFrame | None = None,
        timeframe: str | None = None,
    ) -> ValidationResult:
        """
        Run all validations.

        Args:
            start_date: Start date
            end_date: End date
            candle_series: Optional candle series for coverage validation
            timeframe: Optional timeframe for coverage validation

        Returns:
            ValidationResult
        """
        # Validate window
        window_result = self.validate_window(start_date, end_date)
        if not window_result.valid:
            return window_result

        # Validate data coverage if provided
        if candle_series is not None and timeframe:
            coverage_result = self.validate_data_coverage(candle_series, timeframe, start_date, end_date)
            if not coverage_result.valid:
                return coverage_result

        return ValidationResult(valid=True, details={"all_checks_passed": True})

