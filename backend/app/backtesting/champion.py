"""Persistence helpers for champion campaign records."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.backtesting.sensitivity_guard import SensitivityGuard, StabilityStatus
from app.core.database import SessionLocal
from app.core.logging import logger
from app.db import crud

# Maximum annualized tracking error threshold for champion acceptance (3%)
MAX_ANNUALIZED_TRACKING_ERROR_PCT = 3.0


def _check_sensitivity_stability(
    record: dict[str, Any],
    sensitivity_results_path: Path | str | None = None,
    *,
    enable_guard: bool = True,
    guard_config: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    """
    Check sensitivity stability before promoting champion.
    
    Args:
        record: Champion promotion record
        sensitivity_results_path: Path to sensitivity results parquet file
        enable_guard: Whether to enable sensitivity guard (default: True)
        guard_config: Optional configuration for SensitivityGuard
        
    Returns:
        Tuple of (is_stable, rejection_reason)
    """
    if not enable_guard:
        return True, None
    
    # Try to find sensitivity results
    if sensitivity_results_path is None:
        # Try to find results based on params_id and dates
        params_id = record.get("params_id", "")
        start_date = record.get("start_date", "")
        end_date = record.get("end_date", "")
        
        # Try common locations
        possible_paths = [
            Path("artifacts/sensitivity") / f"{params_id}.parquet",
            Path("backend/artifacts/sensitivity") / f"{params_id}.parquet",
            Path("data/sensitivity") / f"{params_id}.parquet",
        ]
        
        for path in possible_paths:
            if path.exists():
                sensitivity_results_path = path
                break
    
    if sensitivity_results_path is None or not Path(sensitivity_results_path).exists():
        logger.warning(
            "Sensitivity results not found, skipping stability check",
            extra={
                "params_id": record.get("params_id"),
                "sensitivity_results_path": str(sensitivity_results_path) if sensitivity_results_path else None,
            },
        )
        # If guard is enabled but results don't exist, we could either:
        # 1. Reject (strict mode)
        # 2. Warn and allow (lenient mode - current)
        # For now, we'll allow but log a warning
        return True, None
    
    # Evaluate stability
    guard_config = guard_config or {}
    guard = SensitivityGuard(**guard_config)
    
    campaign_id = record.get("params_id", "unknown")
    base_params_id = record.get("params_id")
    
    report = guard.load_and_evaluate(
        sensitivity_results_path,
        campaign_id=campaign_id,
        base_params_id=base_params_id,
    )
    
    if report.status == StabilityStatus.UNSTABLE:
        reasons = "; ".join(report.rejection_reasons)
        logger.error(
            "Champion promotion rejected due to sensitivity instability",
            extra={
                "params_id": record.get("params_id"),
                "campaign_id": campaign_id,
                "reasons": reasons,
                "max_calmar_degradation": report.max_calmar_degradation_pct,
                "max_sharpe_degradation": report.max_sharpe_degradation_pct,
                "anova_p_value": report.anova_p_value,
            },
        )
        return False, reasons
    
    if report.status == StabilityStatus.INSUFFICIENT_DATA:
        logger.warning(
            "Insufficient sensitivity data, allowing promotion with warning",
            extra={
                "params_id": record.get("params_id"),
                "reasons": "; ".join(report.rejection_reasons),
            },
        )
        # Allow promotion but log warning
        return True, None
    
    logger.info(
        "Sensitivity stability check passed",
        extra={
            "params_id": record.get("params_id"),
            "campaign_id": campaign_id,
            "base_calmar": report.base_calmar,
            "max_calmar_degradation": report.max_calmar_degradation_pct,
            "calmar_std": report.calmar_std,
        },
    )
    return True, None


def _check_tracking_error(
    record: dict[str, Any],
    *,
    max_annualized_tracking_error_pct: float = MAX_ANNUALIZED_TRACKING_ERROR_PCT,
    max_rmse_pct: float = 0.05,  # 5% default
) -> tuple[bool, str | None]:
    """
    Check tracking error before promoting champion.
    
    Checks both annualized tracking error and RMSE from tracking_error_stats.
    
    Args:
        record: Champion promotion record
        max_annualized_tracking_error_pct: Maximum annualized tracking error threshold (default: 3%)
        max_rmse_pct: Maximum RMSE as percentage of initial capital (default: 5%)
        
    Returns:
        Tuple of (is_valid, rejection_reason)
    """
    from app.backtesting.guardrails import GuardrailChecker, GuardrailConfig
    
    # Extract tracking error data from metrics or base_result
    metrics = record.get("metrics", {})
    base_result = record.get("base_result", {})
    
    # Get initial capital for RMSE percentage calculation
    initial_capital = base_result.get("initial_capital") or metrics.get("initial_capital") or 10000.0
    
    # Try to get tracking_error_stats (preferred) or tracking_error_summary
    tracking_error_stats = (
        base_result.get("tracking_error_stats") or
        metrics.get("tracking_error_stats") or
        record.get("tracking_error_stats")
    )
    
    tracking_error_summary = (
        metrics.get("tracking_error_summary") or 
        base_result.get("tracking_error_summary") or
        record.get("tracking_error_summary")
    )
    
    # Use GuardrailChecker for consistent evaluation
    guard_config = GuardrailConfig(
        max_tracking_error_annualized_pct=max_annualized_tracking_error_pct / 100.0,  # Convert to decimal
        max_tracking_error_rmse_pct=max_rmse_pct,
    )
    checker = GuardrailChecker(guard_config)
    
    # Check RMSE from tracking_error_stats (preferred method)
    if tracking_error_stats and isinstance(tracking_error_stats, list) and len(tracking_error_stats) > 0:
        rmse_result = checker.check_tracking_error_rmse(tracking_error_stats, initial_capital)
        if not rmse_result.passed:
            rejection_reason = (
                f"Tracking error RMSE ({rmse_result.details.get('rmse_pct', 0) * 100:.2f}%) exceeds maximum threshold "
                f"({max_rmse_pct * 100:.0f}%)"
            )
            logger.error(
                "Champion promotion rejected due to excessive tracking error RMSE",
                extra={
                    "params_id": record.get("params_id"),
                    "rmse_pct": rmse_result.details.get("rmse_pct", 0),
                    "threshold_pct": max_rmse_pct,
                },
            )
            return False, rejection_reason
    
    # Fallback: Check annualized tracking error from summary
    if tracking_error_summary and isinstance(tracking_error_summary, dict):
        annualized_tracking_error = tracking_error_summary.get("annualized_tracking_error")
        if annualized_tracking_error is not None:
            # Convert to percentage if needed
            if annualized_tracking_error > 1.0:
                # Likely absolute value, convert to percentage
                if initial_capital > 0:
                    annualized_tracking_error_pct = (annualized_tracking_error / initial_capital) * 100.0
                else:
                    annualized_tracking_error_pct = 0.0
            else:
                # Already a percentage
                annualized_tracking_error_pct = annualized_tracking_error * 100.0
            
            # Check threshold
            if annualized_tracking_error_pct > max_annualized_tracking_error_pct:
                rejection_reason = (
                    f"Annualized tracking error ({annualized_tracking_error_pct:.2f}%) exceeds maximum threshold "
                    f"({max_annualized_tracking_error_pct}%)"
                )
                logger.error(
                    "Champion promotion rejected due to excessive annualized tracking error",
                    extra={
                        "params_id": record.get("params_id"),
                        "annualized_tracking_error_pct": annualized_tracking_error_pct,
                        "threshold_pct": max_annualized_tracking_error_pct,
                    },
                )
                return False, rejection_reason
    
    # If no tracking error data available, log warning but allow promotion
    if not tracking_error_stats and not tracking_error_summary:
        logger.warning(
            "No tracking error data found in campaign record, skipping tracking error check",
            extra={"params_id": record.get("params_id")},
        )
        return True, None
    
    logger.info(
        "Tracking error check passed",
        extra={
            "params_id": record.get("params_id"),
            "has_tracking_error_stats": bool(tracking_error_stats),
            "has_tracking_error_summary": bool(tracking_error_summary),
        },
    )
    return True, None


def persist_campaign_record(
    record: dict[str, Any],
    *,
    enable_sensitivity_guard: bool = True,
    sensitivity_results_path: Path | str | None = None,
    guard_config: dict[str, Any] | None = None,
    enable_tracking_error_check: bool = True,
    max_annualized_tracking_error_pct: float = MAX_ANNUALIZED_TRACKING_ERROR_PCT,
) -> None:
    """
    Persist campaign evaluation records, promoting champions when required.
    
    Args:
        record: Campaign record dictionary
        enable_sensitivity_guard: Whether to check sensitivity stability (default: True)
        sensitivity_results_path: Path to sensitivity results parquet file
        guard_config: Optional configuration for SensitivityGuard
        enable_tracking_error_check: Whether to check tracking error (default: True)
        max_annualized_tracking_error_pct: Maximum annualized tracking error threshold (default: 3%)
    """
    if not record:
        return

    status = record.get("status")
    if status != "improved":
        return

    # Check tracking error before promoting
    if enable_tracking_error_check:
        is_valid, rejection_reason = _check_tracking_error(
            record,
            max_annualized_tracking_error_pct=max_annualized_tracking_error_pct,
        )
        
        if not is_valid:
            logger.error(
                "Champion promotion aborted due to excessive tracking error",
                extra={
                    "params_id": record.get("params_id"),
                    "rejection_reason": rejection_reason,
                },
            )
            # Store rejection reason in record for audit
            record["tracking_error_check"] = {
                "passed": False,
                "rejection_reason": rejection_reason,
            }
            # Don't promote
            return
        
        # Mark tracking error check as passed
        record["tracking_error_check"] = {
            "passed": True,
            "rejection_reason": None,
        }

    # Check sensitivity stability before promoting
    if enable_sensitivity_guard:
        is_stable, rejection_reason = _check_sensitivity_stability(
            record,
            sensitivity_results_path=sensitivity_results_path,
            enable_guard=True,
            guard_config=guard_config,
        )
        
        if not is_stable:
            logger.error(
                "Champion promotion aborted due to sensitivity instability",
                extra={
                    "params_id": record.get("params_id"),
                    "rejection_reason": rejection_reason,
                },
            )
            # Store rejection reason in record for audit
            record["sensitivity_check"] = {
                "passed": False,
                "rejection_reason": rejection_reason,
            }
            # Don't promote, but we could store this as a failed promotion attempt
            return

    with SessionLocal() as db:
        try:
            # Add sensitivity check result to record
            if enable_sensitivity_guard:
                record["sensitivity_check"] = {
                    "passed": True,
                    "rejection_reason": None,
                }
            
            champion = crud.record_champion_promotion(db, record)
            logger.info(
                "Champion promoted",
                extra={
                    "params_id": champion.params_id,
                    "score": champion.score,
                    "objective": champion.objective,
                    "promoted_at": champion.promoted_at.isoformat(),
                    "sensitivity_check_passed": enable_sensitivity_guard,
                    "tracking_error_check_passed": enable_tracking_error_check,
                },
            )
        except Exception as exc:
            logger.exception("Failed to persist champion promotion", extra={"error": str(exc)})




