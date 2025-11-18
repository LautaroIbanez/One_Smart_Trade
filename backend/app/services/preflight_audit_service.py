"""Preflight audit service to validate all requirements before publishing recommendations."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from app.core.config import settings
from app.core.exceptions import DataFreshnessError, DataGapError
from app.core.logging import logger
from app.data.curation import DataCuration
from app.data.signal_data_provider import SignalDataProvider


@dataclass
class AuditCheck:
    """Result of a single audit check."""
    
    name: str
    passed: bool
    message: str
    details: dict[str, Any] | None = None


@dataclass
class PreflightAuditResult:
    """Result of preflight audit."""
    
    all_checks_passed: bool
    checks: list[AuditCheck]
    recommendation_id: int | None = None
    signal_payload: dict[str, Any] | None = None
    
    def get_failed_checks(self) -> list[AuditCheck]:
        """Get list of failed checks."""
        return [check for check in self.checks if not check.passed]
    
    def get_passed_checks(self) -> list[AuditCheck]:
        """Get list of passed checks."""
        return [check for check in self.checks if check.passed]
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging/API responses."""
        return {
            "all_checks_passed": self.all_checks_passed,
            "total_checks": len(self.checks),
            "passed_checks": len(self.get_passed_checks()),
            "failed_checks": len(self.get_failed_checks()),
            "checks": [
                {
                    "name": check.name,
                    "passed": check.passed,
                    "message": check.message,
                    "details": check.details,
                }
                for check in self.checks
            ],
            "recommendation_id": self.recommendation_id,
        }


class PreflightAuditService:
    """Service to perform preflight audit before publishing recommendations."""
    
    def __init__(self):
        """Initialize preflight audit service."""
        self.curation = DataCuration()
        self.data_provider = SignalDataProvider(
            curation=self.curation,
            venue="binance",
            symbol="BTCUSDT",
        )
    
    async def audit_recommendation(
        self,
        signal_payload: dict[str, Any],
        *,
        recommendation_id: int | None = None,
    ) -> PreflightAuditResult:
        """
        Perform complete preflight audit on a recommendation before publishing.
        
        Validates:
        1. Data freshness
        2. Data gaps
        3. Seed fixed
        4. Backtest ok
        5. KPIs > threshold
        6. Execution plan ready
        
        Args:
            signal_payload: Signal payload to audit
            recommendation_id: Optional recommendation ID if already created
            
        Returns:
            PreflightAuditResult with all check results
        """
        checks: list[AuditCheck] = []
        
        # Check 1: Data Freshness
        data_freshness_check = await self._check_data_freshness()
        checks.append(data_freshness_check)
        logger.info(f"Data freshness check: {'PASSED' if data_freshness_check.passed else 'FAILED'} - {data_freshness_check.message}")
        
        # Check 2: Data Gaps
        data_gaps_check = await self._check_data_gaps()
        checks.append(data_gaps_check)
        logger.info(f"Data gaps check: {'PASSED' if data_gaps_check.passed else 'FAILED'} - {data_gaps_check.message}")
        
        # Check 3: Seed Fixed
        seed_check = self._check_seed_fixed(signal_payload)
        checks.append(seed_check)
        logger.info(f"Seed fixed check: {'PASSED' if seed_check.passed else 'FAILED'} - {seed_check.message}")
        
        # Check 4: Backtest OK
        backtest_check = self._check_backtest_ok(signal_payload)
        checks.append(backtest_check)
        logger.info(f"Backtest check: {'PASSED' if backtest_check.passed else 'FAILED'} - {backtest_check.message}")
        
        # Check 5: KPIs > Threshold
        kpi_check = self._check_kpis_above_threshold(signal_payload)
        checks.append(kpi_check)
        logger.info(f"KPI check: {'PASSED' if kpi_check.passed else 'FAILED'} - {kpi_check.message}")
        
        # Check 6: Execution Plan Ready
        execution_plan_check = self._check_execution_plan_ready(signal_payload)
        checks.append(execution_plan_check)
        logger.info(f"Execution plan check: {'PASSED' if execution_plan_check.passed else 'FAILED'} - {execution_plan_check.message}")
        
        all_passed = all(check.passed for check in checks)
        
        if all_passed:
            logger.info("✅ All preflight audit checks PASSED - recommendation ready for publication")
        else:
            failed_checks = [check.name for check in checks if not check.passed]
            logger.error(f"❌ Preflight audit FAILED - failed checks: {', '.join(failed_checks)}")
        
        return PreflightAuditResult(
            all_checks_passed=all_passed,
            checks=checks,
            recommendation_id=recommendation_id,
            signal_payload=signal_payload,
        )
    
    async def _check_data_freshness(self) -> AuditCheck:
        """Check that data is fresh (within threshold)."""
        try:
            # Use SignalDataProvider to validate freshness
            inputs = self.data_provider.get_validated_inputs(
                validate_freshness=True,
                validate_gaps=False,  # Don't fail on gaps for this check
            )
            
            # Check latest timestamp
            df_1h = inputs.df_1h
            if df_1h.empty:
                return AuditCheck(
                    name="data_freshness",
                    passed=False,
                    message="No hourly data available",
                    details={"error": "df_1h is empty"},
                )
            
            latest_timestamp = df_1h.index[-1] if hasattr(df_1h.index[-1], "to_pydatetime") else pd.Timestamp(df_1h.index[-1])
            if hasattr(latest_timestamp, "to_pydatetime"):
                latest_dt = latest_timestamp.to_pydatetime()
            else:
                latest_dt = pd.Timestamp(latest_timestamp).to_pydatetime()
            
            now = datetime.utcnow()
            age_minutes = (now - latest_dt).total_seconds() / 60.0
            
            threshold_minutes = settings.DATA_FRESHNESS_THRESHOLD_MINUTES
            
            if age_minutes > threshold_minutes:
                return AuditCheck(
                    name="data_freshness",
                    passed=False,
                    message=f"Data is stale: {age_minutes:.1f} minutes old (threshold: {threshold_minutes} minutes)",
                    details={
                        "latest_timestamp": latest_dt.isoformat(),
                        "age_minutes": round(age_minutes, 1),
                        "threshold_minutes": threshold_minutes,
                    },
                )
            
            return AuditCheck(
                name="data_freshness",
                passed=True,
                message=f"Data is fresh: {age_minutes:.1f} minutes old (threshold: {threshold_minutes} minutes)",
                details={
                    "latest_timestamp": latest_dt.isoformat(),
                    "age_minutes": round(age_minutes, 1),
                    "threshold_minutes": threshold_minutes,
                },
            )
        except DataFreshnessError as e:
            return AuditCheck(
                name="data_freshness",
                passed=False,
                message=f"Data freshness validation failed: {e.reason}",
                details={
                    "error": str(e),
                    "interval": e.interval,
                    "latest_timestamp": e.latest_timestamp,
                    "threshold_minutes": e.threshold_minutes,
                },
            )
        except Exception as e:
            logger.error(f"Error checking data freshness: {e}", exc_info=True)
            return AuditCheck(
                name="data_freshness",
                passed=False,
                message=f"Error checking data freshness: {str(e)}",
                details={"error": str(e)},
            )
    
    async def _check_data_gaps(self) -> AuditCheck:
        """Check that data has no gaps exceeding tolerance threshold."""
        try:
            # Use SignalDataProvider to validate gaps
            inputs = self.data_provider.get_validated_inputs(
                validate_freshness=False,  # Don't check freshness here (separate check)
                validate_gaps=True,  # Validate gaps
            )
            
            # If we get here, gaps validation passed
            return AuditCheck(
                name="data_gaps",
                passed=True,
                message="Data gap validation passed: no critical gaps detected",
                details={
                    "tolerance_candles": settings.DATA_GAP_TOLERANCE_CANDLES,
                    "lookback_days": settings.DATA_GAP_CHECK_LOOKBACK_DAYS,
                },
            )
        except DataGapError as e:
            return AuditCheck(
                name="data_gaps",
                passed=False,
                message=f"Data gap validation failed: {e.reason}",
                details={
                    "error": str(e),
                    "interval": e.interval,
                    "gaps": e.gaps,
                    "tolerance_candles": e.tolerance_candles,
                    "context": e.context_data,
                },
            )
        except Exception as e:
            logger.error(f"Error checking data gaps: {e}", exc_info=True)
            return AuditCheck(
                name="data_gaps",
                passed=False,
                message=f"Error checking data gaps: {str(e)}",
                details={"error": str(e)},
            )
    
    def _check_seed_fixed(self, signal_payload: dict[str, Any]) -> AuditCheck:
        """Check that seed is fixed and present in signal payload."""
        seed = signal_payload.get("seed")
        
        if seed is None:
            return AuditCheck(
                name="seed_fixed",
                passed=False,
                message="Seed is missing from signal payload",
                details={"seed": None},
            )
        
        if not isinstance(seed, int):
            return AuditCheck(
                name="seed_fixed",
                passed=False,
                message=f"Seed is not an integer: {type(seed)}",
                details={"seed": seed, "seed_type": str(type(seed))},
            )
        
        # Verify seed is deterministic (should be positive integer)
        if seed < 0:
            return AuditCheck(
                name="seed_fixed",
                passed=False,
                message=f"Seed is negative: {seed}",
                details={"seed": seed},
            )
        
        return AuditCheck(
            name="seed_fixed",
            passed=True,
            message=f"Seed is fixed: {seed}",
            details={"seed": seed},
        )
    
    def _check_backtest_ok(self, signal_payload: dict[str, Any]) -> AuditCheck:
        """Check that backtest results are present and meet requirements."""
        if not settings.BACKTEST_ENABLED:
            return AuditCheck(
                name="backtest_ok",
                passed=True,
                message="Backtest validation is disabled in settings",
                details={"backtest_enabled": False},
            )
        
        backtest_run_id = signal_payload.get("backtest_run_id")
        if not backtest_run_id:
            return AuditCheck(
                name="backtest_ok",
                passed=False,
                message="Backtest run ID is missing",
                details={"backtest_run_id": None},
            )
        
        # Check backtest metrics
        backtest_cagr = signal_payload.get("backtest_cagr")
        backtest_win_rate = signal_payload.get("backtest_win_rate")
        backtest_risk_reward_ratio = signal_payload.get("backtest_risk_reward_ratio")
        backtest_max_drawdown = signal_payload.get("backtest_max_drawdown")
        
        if backtest_cagr is None:
            return AuditCheck(
                name="backtest_ok",
                passed=False,
                message="Backtest CAGR is missing",
                details={"backtest_run_id": backtest_run_id},
            )
        
        # Validate backtest metrics against thresholds
        min_sharpe = settings.BACKTEST_MIN_SHARPE
        max_drawdown = settings.BACKTEST_MAX_DRAWDOWN_PCT
        
        issues = []
        if backtest_max_drawdown is not None and backtest_max_drawdown > max_drawdown:
            issues.append(f"Max drawdown {backtest_max_drawdown:.2f}% exceeds threshold {max_drawdown:.2f}%")
        
        if issues:
            return AuditCheck(
                name="backtest_ok",
                passed=False,
                message=f"Backtest metrics below threshold: {', '.join(issues)}",
                details={
                    "backtest_run_id": backtest_run_id,
                    "backtest_cagr": backtest_cagr,
                    "backtest_win_rate": backtest_win_rate,
                    "backtest_risk_reward_ratio": backtest_risk_reward_ratio,
                    "backtest_max_drawdown": backtest_max_drawdown,
                    "issues": issues,
                },
            )
        
        return AuditCheck(
            name="backtest_ok",
            passed=True,
            message=f"Backtest passed: run_id={backtest_run_id}, CAGR={backtest_cagr:.2f}%",
            details={
                "backtest_run_id": backtest_run_id,
                "backtest_cagr": backtest_cagr,
                "backtest_win_rate": backtest_win_rate,
                "backtest_risk_reward_ratio": backtest_risk_reward_ratio,
                "backtest_max_drawdown": backtest_max_drawdown,
            },
        )
    
    def _check_kpis_above_threshold(self, signal_payload: dict[str, Any]) -> AuditCheck:
        """Check that KPIs are above minimum thresholds."""
        # Extract KPIs from signal payload
        confidence = signal_payload.get("confidence", 0.0)
        confidence_calibrated = signal_payload.get("confidence_calibrated")
        risk_metrics = signal_payload.get("risk_metrics", {})
        rr_ratio = risk_metrics.get("risk_reward_ratio", 0.0)
        
        # Minimum thresholds
        min_confidence = 30.0  # Minimum confidence threshold
        min_rr_ratio = settings.RR_FLOOR  # Minimum risk/reward ratio
        
        issues = []
        
        # Check confidence
        effective_confidence = confidence_calibrated if confidence_calibrated is not None else confidence
        if effective_confidence < min_confidence:
            issues.append(f"Confidence {effective_confidence:.1f}% below threshold {min_confidence:.1f}%")
        
        # Check risk/reward ratio
        if rr_ratio < min_rr_ratio:
            issues.append(f"Risk/reward ratio {rr_ratio:.2f} below threshold {min_rr_ratio:.2f}")
        
        # Check if signal is HOLD (which is acceptable)
        signal = signal_payload.get("signal", "")
        if signal == "HOLD":
            return AuditCheck(
                name="kpis_above_threshold",
                passed=True,
                message="Signal is HOLD - KPI check skipped",
                details={"signal": "HOLD"},
            )
        
        if issues:
            return AuditCheck(
                name="kpis_above_threshold",
                passed=False,
                message=f"KPIs below threshold: {', '.join(issues)}",
                details={
                    "confidence": confidence,
                    "confidence_calibrated": confidence_calibrated,
                    "risk_reward_ratio": rr_ratio,
                    "min_confidence": min_confidence,
                    "min_rr_ratio": min_rr_ratio,
                    "issues": issues,
                },
            )
        
        return AuditCheck(
            name="kpis_above_threshold",
            passed=True,
            message=f"KPIs above threshold: confidence={effective_confidence:.1f}%, RR={rr_ratio:.2f}",
            details={
                "confidence": confidence,
                "confidence_calibrated": confidence_calibrated,
                "risk_reward_ratio": rr_ratio,
                "min_confidence": min_confidence,
                "min_rr_ratio": min_rr_ratio,
            },
        )
    
    def _check_execution_plan_ready(self, signal_payload: dict[str, Any]) -> AuditCheck:
        """Check that execution plan is ready (for BUY/SELL signals)."""
        signal = signal_payload.get("signal", "")
        
        # HOLD signals don't need execution plan
        if signal == "HOLD":
            return AuditCheck(
                name="execution_plan_ready",
                passed=True,
                message="Signal is HOLD - execution plan not required",
                details={"signal": "HOLD"},
            )
        
        # Check if execution plan exists (should be added by RecommendationService)
        execution_plan = signal_payload.get("execution_plan")
        
        if not execution_plan:
            return AuditCheck(
                name="execution_plan_ready",
                passed=False,
                message="Execution plan is missing",
                details={"signal": signal},
            )
        
        # Validate execution plan structure
        required_fields = ["operational_window", "order_type", "suggested_size", "instructions"]
        missing_fields = [field for field in required_fields if field not in execution_plan]
        
        if missing_fields:
            return AuditCheck(
                name="execution_plan_ready",
                passed=False,
                message=f"Execution plan missing required fields: {', '.join(missing_fields)}",
                details={
                    "signal": signal,
                    "missing_fields": missing_fields,
                    "execution_plan_keys": list(execution_plan.keys()),
                },
            )
        
        return AuditCheck(
            name="execution_plan_ready",
            passed=True,
            message=f"Execution plan ready: order_type={execution_plan.get('order_type')}",
            details={
                "signal": signal,
                "order_type": execution_plan.get("order_type"),
                "has_operational_window": "operational_window" in execution_plan,
                "has_suggested_size": "suggested_size" in execution_plan,
            },
        )

