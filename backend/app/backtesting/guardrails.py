"""Automatic guardrails for rejecting champions based on metrics."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.core.logging import logger


class CampaignRejectedReason(str, Enum):
    """Reasons for campaign rejection."""

    CALMAR_OOS_TOO_LOW = "calmar_oos_too_low"
    MAX_DRAWDOWN_TOO_HIGH = "max_drawdown_too_high"
    RISK_OF_RUIN_TOO_HIGH = "risk_of_ruin_too_high"
    OOS_LENGTH_INSUFFICIENT = "oos_length_insufficient"
    THEORETICAL_REALISTIC_DIVERGENCE = "theoretical_realistic_divergence"
    INSUFFICIENT_TRADES = "insufficient_trades"
    INSUFFICIENT_MONTHS = "insufficient_months"
    UNSTABLE_CALMAR_CI = "unstable_calmar_ci"
    TRACKING_ERROR_TOO_HIGH = "tracking_error_too_high"


@dataclass
class GuardrailConfig:
    """Configuration for guardrails."""

    min_calmar_oos: float = 1.5
    max_drawdown_realistic: float = 0.25  # 25%
    max_risk_of_ruin: float = 0.05  # 5%
    min_oos_length_days: int = 120
    max_cagr_divergence_pct: float = 5.0  # 5% CAGR difference
    min_trades: int = 50
    min_months: int = 24
    min_calmar_ci_low: float = 1.0  # Minimum Calmar CI lower bound
    max_tracking_error_annualized_pct: float = 0.05  # 5% of capital
    max_tracking_error_rmse_pct: float = 0.05  # 5% RMSE as percentage of initial capital


@dataclass
class GuardrailResult:
    """Result of guardrail check."""

    passed: bool
    reason: CampaignRejectedReason | None = None
    details: dict[str, Any] | None = None

    def raise_if_failed(self) -> None:
        """Raise exception if guardrail failed."""
        if not self.passed:
            from app.backtesting.validation import CampaignAbort

            raise CampaignAbort(
                f"Guardrail failed: {self.reason.value if self.reason else 'unknown'}",
                self.details or {},
            )


class GuardrailChecker:
    """Checks guardrails and rejects champions that don't meet criteria."""

    def __init__(self, config: GuardrailConfig | None = None) -> None:
        """
        Initialize guardrail checker.

        Args:
            config: Guardrail configuration (uses defaults if None)
        """
        self.config = config or GuardrailConfig()

    def check_calmar_oos(self, calmar_oos: float) -> GuardrailResult:
        """Check if OOS Calmar meets minimum threshold."""
        if calmar_oos < self.config.min_calmar_oos:
            return GuardrailResult(
                passed=False,
                reason=CampaignRejectedReason.CALMAR_OOS_TOO_LOW,
                details={
                    "calmar_oos": calmar_oos,
                    "min_required": self.config.min_calmar_oos,
                },
            )
        return GuardrailResult(passed=True)

    def check_max_drawdown(self, max_drawdown_pct: float) -> GuardrailResult:
        """Check if max drawdown is within limit."""
        max_dd_decimal = max_drawdown_pct / 100.0 if max_drawdown_pct > 1.0 else max_drawdown_pct

        if max_dd_decimal > self.config.max_drawdown_realistic:
            return GuardrailResult(
                passed=False,
                reason=CampaignRejectedReason.MAX_DRAWDOWN_TOO_HIGH,
                details={
                    "max_drawdown": max_dd_decimal,
                    "max_allowed": self.config.max_drawdown_realistic,
                },
            )
        return GuardrailResult(passed=True)

    def check_risk_of_ruin(self, risk_of_ruin: float) -> GuardrailResult:
        """Check if risk of ruin is within limit."""
        if risk_of_ruin > self.config.max_risk_of_ruin:
            return GuardrailResult(
                passed=False,
                reason=CampaignRejectedReason.RISK_OF_RUIN_TOO_HIGH,
                details={
                    "risk_of_ruin": risk_of_ruin,
                    "max_allowed": self.config.max_risk_of_ruin,
                },
            )
        return GuardrailResult(passed=True)

    def check_oos_length(self, oos_length_days: int) -> GuardrailResult:
        """Check if OOS period is long enough."""
        if oos_length_days < self.config.min_oos_length_days:
            return GuardrailResult(
                passed=False,
                reason=CampaignRejectedReason.OOS_LENGTH_INSUFFICIENT,
                details={
                    "oos_length_days": oos_length_days,
                    "min_required": self.config.min_oos_length_days,
                },
            )
        return GuardrailResult(passed=True)

    def check_cagr_divergence(
        self,
        cagr_theoretical: float,
        cagr_realistic: float,
    ) -> GuardrailResult:
        """Check if theoretical and realistic CAGR diverge too much."""
        divergence_pct = abs(cagr_theoretical - cagr_realistic)

        if divergence_pct > self.config.max_cagr_divergence_pct:
            return GuardrailResult(
                passed=False,
                reason=CampaignRejectedReason.THEORETICAL_REALISTIC_DIVERGENCE,
                details={
                    "cagr_theoretical": cagr_theoretical,
                    "cagr_realistic": cagr_realistic,
                    "divergence_pct": divergence_pct,
                    "max_allowed": self.config.max_cagr_divergence_pct,
                },
            )
        return GuardrailResult(passed=True)

    def check_trade_count(self, trade_count: int) -> GuardrailResult:
        """Check if there are enough trades."""
        if trade_count < self.config.min_trades:
            return GuardrailResult(
                passed=False,
                reason=CampaignRejectedReason.INSUFFICIENT_TRADES,
                details={
                    "trade_count": trade_count,
                    "min_required": self.config.min_trades,
                },
            )
        return GuardrailResult(passed=True)

    def check_tracking_error(self, tracking_error_annualized_pct: float) -> GuardrailResult:
        """Check if annualized tracking error exceeds configured threshold."""
        if tracking_error_annualized_pct > self.config.max_tracking_error_annualized_pct:
            return GuardrailResult(
                passed=False,
                reason=CampaignRejectedReason.TRACKING_ERROR_TOO_HIGH,
                details={
                    "tracking_error_annualized_pct": tracking_error_annualized_pct,
                    "max_allowed_pct": self.config.max_tracking_error_annualized_pct,
                },
            )
        return GuardrailResult(passed=True)

    def check_tracking_error_rmse(
        self,
        tracking_error_stats: list[dict[str, Any]],
        initial_capital: float,
    ) -> GuardrailResult:
        """
        Check if RMSE from tracking_error_stats exceeds configured threshold.
        
        Args:
            tracking_error_stats: List of tracking error stats dictionaries from engine
            initial_capital: Initial capital for percentage calculation
            
        Returns:
            GuardrailResult
        """
        if not tracking_error_stats or initial_capital <= 0:
            return GuardrailResult(passed=True)  # Skip if no data
        
        # Get the latest tracking error stats (most recent calculation)
        latest_stats = tracking_error_stats[-1] if tracking_error_stats else {}
        rmse = latest_stats.get("rmse", 0.0)
        
        if rmse <= 0:
            return GuardrailResult(passed=True)  # Skip if RMSE not available
        
        # Calculate RMSE as percentage of initial capital
        rmse_pct = (rmse / initial_capital) if initial_capital > 0 else 0.0
        
        if rmse_pct > self.config.max_tracking_error_rmse_pct:
            return GuardrailResult(
                passed=False,
                reason=CampaignRejectedReason.TRACKING_ERROR_TOO_HIGH,
                details={
                    "rmse": rmse,
                    "rmse_pct": rmse_pct,
                    "initial_capital": initial_capital,
                    "max_allowed_rmse_pct": self.config.max_tracking_error_rmse_pct,
                },
            )
        return GuardrailResult(passed=True)

    def check_calmar_ci_stability(self, calmar_ci_low: float | None) -> GuardrailResult:
        """Check if Calmar confidence interval lower bound meets threshold."""
        if calmar_ci_low is None:
            return GuardrailResult(passed=True)  # Skip if CI not available

        if calmar_ci_low < self.config.min_calmar_ci_low:
            return GuardrailResult(
                passed=False,
                reason=CampaignRejectedReason.UNSTABLE_CALMAR_CI,
                details={
                    "calmar_ci_low": calmar_ci_low,
                    "min_required": self.config.min_calmar_ci_low,
                },
            )
        return GuardrailResult(passed=True)

    def check_history_length(self, duration_days: int) -> GuardrailResult:
        """Check if history is long enough."""
        months = duration_days / 30.0

        if months < self.config.min_months:
            return GuardrailResult(
                passed=False,
                reason=CampaignRejectedReason.INSUFFICIENT_MONTHS,
                details={
                    "duration_days": duration_days,
                    "months": months,
                    "min_required_months": self.config.min_months,
                },
            )
        return GuardrailResult(passed=True)

    def check_all(
        self,
        *,
        calmar_oos: float | None = None,
        max_drawdown_pct: float | None = None,
        risk_of_ruin: float | None = None,
        oos_length_days: int | None = None,
        cagr_theoretical: float | None = None,
        cagr_realistic: float | None = None,
        trade_count: int | None = None,
        duration_days: int | None = None,
        calmar_ci_low: float | None = None,
        tracking_error_annualized_pct: float | None = None,
        tracking_error_stats: list[dict[str, Any]] | None = None,
        initial_capital: float | None = None,
    ) -> GuardrailResult:
        """
        Run all applicable guardrail checks.

        Args:
            calmar_oos: OOS Calmar ratio
            max_drawdown_pct: Max drawdown percentage
            risk_of_ruin: Risk of ruin probability
            oos_length_days: OOS period length in days
            cagr_theoretical: Theoretical CAGR
            cagr_realistic: Realistic CAGR
            trade_count: Number of trades
            duration_days: Total duration in days

        Returns:
            GuardrailResult
        """
        checks = []

        if calmar_oos is not None:
            checks.append(self.check_calmar_oos(calmar_oos))

        if max_drawdown_pct is not None:
            checks.append(self.check_max_drawdown(max_drawdown_pct))

        if risk_of_ruin is not None:
            checks.append(self.check_risk_of_ruin(risk_of_ruin))

        if oos_length_days is not None:
            checks.append(self.check_oos_length(oos_length_days))

        if cagr_theoretical is not None and cagr_realistic is not None:
            checks.append(self.check_cagr_divergence(cagr_theoretical, cagr_realistic))

        if trade_count is not None:
            checks.append(self.check_trade_count(trade_count))

        if duration_days is not None:
            checks.append(self.check_history_length(duration_days))

        if calmar_ci_low is not None:
            checks.append(self.check_calmar_ci_stability(calmar_ci_low))

        if tracking_error_annualized_pct is not None:
            checks.append(self.check_tracking_error(tracking_error_annualized_pct))

        if tracking_error_stats is not None and initial_capital is not None:
            checks.append(self.check_tracking_error_rmse(tracking_error_stats, initial_capital))

        # Find first failure
        for check in checks:
            if not check.passed:
                return check

        return GuardrailResult(passed=True, details={"all_checks_passed": True})

