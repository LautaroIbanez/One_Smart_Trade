"""Campaign optimizer tracking objective-driven improvements."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from app.backtesting.engine import BacktestEngine, BacktestRunRequest
from app.backtesting.guardrails import GuardrailChecker, GuardrailConfig
from app.backtesting.metrics import calculate_metrics
from app.backtesting.objectives import CalmarUnderDrawdown, Objective
from app.backtesting.tracking_error import TrackingErrorCalculator
from app.backtesting.validation import CampaignAbort, CampaignValidator
from app.backtesting.walk_forward import WalkForwardPipeline
from app.core.logging import logger

# Maximum annualized tracking error threshold for candidate acceptance (3%)
MAX_ANNUALIZED_TRACKING_ERROR_PCT = 3.0

PersistRecordFn = Callable[[dict[str, Any]], None]


@dataclass(slots=True)
class CandidateResult:
    """Backtest outcome for a single parameter variant."""

    params_id: str
    start_date: datetime
    end_date: datetime
    metrics: dict[str, float]
    score: float
    objective_value: float
    engine_args: dict[str, Any] = field(default_factory=dict)
    execution_overrides: dict[str, Any] = field(default_factory=dict)
    status: str = field(default="pending")


class CampaignOptimizer:
    """Run parameter campaigns and retain the best candidate per objective."""

    def __init__(
        self,
        objective: Objective | None = None,
        persist_fn: PersistRecordFn | None = None,
        *,
        max_ruin_probability: float | None = None,
        max_negative_month_prob: float | None = None,
        max_annualized_tracking_error_pct: float | None = None,
        enable_validation: bool = True,
        enable_guardrails: bool = True,
        enable_walk_forward: bool = False,
        guardrail_config: GuardrailConfig | None = None,
    ) -> None:
        """
        Initialize campaign optimizer.

        Args:
            objective: Objective function (default: CalmarUnderDrawdown)
            persist_fn: Function to persist records
            max_ruin_probability: Max ruin probability filter
            max_negative_month_prob: Max negative month probability filter
            max_annualized_tracking_error_pct: Max annualized tracking error filter (default: 3%)
            enable_validation: Enable pre-execution validation (default: True)
            enable_guardrails: Enable guardrail checks (default: True)
            enable_walk_forward: Enable walk-forward analysis (default: False)
            guardrail_config: Guardrail configuration (uses defaults if None)
        """
        self.objective = objective or CalmarUnderDrawdown()
        self.persist_fn = persist_fn
        self.best: CandidateResult | None = None
        self.records: list[dict[str, Any]] = []
        self.max_ruin_probability = max_ruin_probability
        self.max_negative_month_prob = max_negative_month_prob
        self.max_annualized_tracking_error_pct = max_annualized_tracking_error_pct or MAX_ANNUALIZED_TRACKING_ERROR_PCT
        self.enable_validation = enable_validation
        self.enable_guardrails = enable_guardrails
        self.enable_walk_forward = enable_walk_forward
        self.validator = CampaignValidator() if enable_validation else None
        self.guardrail_checker = GuardrailChecker(guardrail_config) if enable_guardrails else None
        self.walk_forward_pipeline = WalkForwardPipeline() if enable_walk_forward else None

    async def evaluate(
        self,
        *,
        start,
        end,
        params_variants: Iterable[dict[str, Any]],
    ) -> list[CandidateResult]:
        """Execute backtests over multiple parameter variants."""
        results: list[CandidateResult] = []
        for variant in params_variants:
            params_id = variant.get("id")
            if params_id is None:
                logger.warning("Skipping candidate without identifier", extra={"variant": variant})
                continue
            execution_overrides = variant.get("execution_overrides", {})
            engine_args = variant.get("engine_args", {})

            # Pre-execution validation
            if self.validator:
                try:
                    start_ts = pd.to_datetime(start) if not isinstance(start, pd.Timestamp) else start
                    end_ts = pd.to_datetime(end) if not isinstance(end, pd.Timestamp) else end
                    validation_result = self.validator.validate_window(start_ts, end_ts)
                    validation_result.raise_if_invalid()
                except CampaignAbort as exc:
                    logger.warning(
                        "Campaign validation failed",
                        extra={"params_id": params_id, "reason": exc.reason, "details": exc.details},
                    )
                    continue

            try:
                engine = BacktestEngine(**execution_overrides)
                backtest_result = await engine.run_backtest(start, end, **engine_args)
            except CampaignAbort as exc:
                logger.warning(
                    "Campaign aborted",
                    extra={"params_id": params_id, "reason": exc.reason, "details": exc.details},
                )
                continue
            except Exception as exc:
                logger.warning(
                    "Campaign candidate failed during backtest",
                    extra={"params_id": variant.get("id"), "error": str(exc)},
                )
                continue

            if "error" in backtest_result:
                logger.warning(
                    "Backtest returned application error",
                    extra={"params_id": variant.get("id"), "error": backtest_result.get("error_type")},
                )
                continue

            metrics = calculate_metrics(backtest_result)
            # Optional pre-filtering by ruin probability or negative month probability (approx)
            if self.max_ruin_probability is not None:
                ruin_prob = metrics.get("risk_of_ruin") or metrics.get("ruin_simulation", {}).get("ruin_probability")
                if ruin_prob is not None and ruin_prob > self.max_ruin_probability:
                    logger.info("Candidate filtered by ruin probability", extra={"params_id": params_id, "ruin_prob": ruin_prob})
                    continue
            if self.max_negative_month_prob is not None:
                neg_prob = metrics.get("negative_month_prob_approx")
                if neg_prob is not None and neg_prob > self.max_negative_month_prob:
                    logger.info("Candidate filtered by negative month probability", extra={"params_id": params_id, "negative_month_prob": neg_prob})
                    continue
            
            # Check tracking error if enabled
            if self.max_annualized_tracking_error_pct is not None:
                tracking_error = backtest_result.get("tracking_error")
                equity_theoretical = backtest_result.get("equity_theoretical", [])
                equity_realistic = backtest_result.get("equity_realistic", [])
                
                if equity_theoretical and equity_realistic and len(equity_theoretical) > 1 and len(equity_realistic) > 1:
                    # Get timeframe from engine args or result metadata
                    timeframe = engine_args.get("timeframe") or backtest_result.get("metadata", {}).get("timeframe", "1d")
                    bars_per_year_map = {
                        "15m": 365 * 24 * 4,
                        "30m": 365 * 24 * 2,
                        "1h": 365 * 24,
                        "4h": 365 * 6,
                        "1d": 365,
                        "1w": 52,
                    }
                    bars_per_year = bars_per_year_map.get(timeframe, 365)
                    
                    tracking_error_calc = TrackingErrorCalculator.from_curves(
                        theoretical=equity_theoretical,
                        realistic=equity_realistic,
                        bars_per_year=bars_per_year,
                    )
                    
                    # Convert annualized tracking error to percentage
                    annualized_te = tracking_error_calc.annualized_tracking_error
                    initial_capital = backtest_result.get("initial_capital", 10000.0)
                    if initial_capital > 0 and annualized_te > 1.0:
                        # Likely absolute value, convert to percentage
                        annualized_te_pct = (annualized_te / initial_capital) * 100.0
                    else:
                        # Already a percentage
                        annualized_te_pct = annualized_te * 100.0 if annualized_te <= 1.0 else annualized_te
                    
                    if annualized_te_pct > self.max_annualized_tracking_error_pct:
                        logger.info(
                            "Candidate filtered by tracking error",
                            extra={
                                "params_id": params_id,
                                "annualized_tracking_error_pct": annualized_te_pct,
                                "threshold_pct": self.max_annualized_tracking_error_pct,
                            },
                        )
                        continue
                    
                    # Store tracking error summary in metrics for persistence
                    metrics["tracking_error_summary"] = tracking_error_calc.to_dict()
            # Guardrail checks
            if self.guardrail_checker:
                duration_days = (pd.to_datetime(end) - pd.to_datetime(start)).days
                # Extract Calmar CI if available
                calmar_ci_low = None
                if "confidence_intervals" in metrics and "calmar" in metrics.get("confidence_intervals", {}):
                    calmar_ci_low = metrics["confidence_intervals"]["calmar"].get("p5")
                
                # Get tracking error stats for RMSE check
                tracking_error_stats = backtest_result.get("tracking_error_stats", [])
                initial_capital = backtest_result.get("initial_capital", 10000.0)
                
                guardrail_result = self.guardrail_checker.check_all(
                    max_drawdown_pct=metrics.get("max_drawdown"),
                    risk_of_ruin=metrics.get("risk_of_ruin"),
                    trade_count=metrics.get("total_trades", 0),
                    duration_days=duration_days,
                    calmar_ci_low=calmar_ci_low,
                )
                if not guardrail_result.passed:
                    logger.info(
                        "Candidate rejected by guardrails",
                        extra={"params_id": params_id, "reason": guardrail_result.reason, "details": guardrail_result.details},
                    )
                    continue
                
                # Check tracking error RMSE guardrail if tracking_error_stats available
                if tracking_error_stats and initial_capital > 0:
                    rmse_result = self.guardrail_checker.check_tracking_error_rmse(
                        tracking_error_stats=tracking_error_stats,
                        initial_capital=initial_capital,
                    )
                    if not rmse_result.passed:
                        logger.info(
                            "Candidate rejected by tracking error RMSE guardrail",
                            extra={
                                "params_id": params_id,
                                "reason": rmse_result.reason,
                                "details": rmse_result.details,
                            },
                        )
                        continue

            score = self.objective.score(metrics)
            objective_value = metrics.get(self.objective.config.target_metric, 0.0)

            candidate = CandidateResult(
                params_id=params_id,
                start_date=start,
                end_date=end,
                metrics=metrics,
                score=score,
                objective_value=objective_value,
                engine_args=dict(engine_args),
                execution_overrides=dict(execution_overrides),
            )

            status = self._determine_status(candidate)
            candidate.status = status
            results.append(candidate)
            self._persist_record(candidate)

            if status == "improved":
                self.best = candidate

        return results

    def _determine_status(self, candidate: CandidateResult) -> str:
        """Classify candidate relative to the current best."""
        if not self.objective.is_valid(candidate.metrics):
            return "invalid"

        if self.best is None:
            return "improved"

        improvement_threshold = self.best.score * (1 + self.objective.config.min_improvement)
        if candidate.score > improvement_threshold:
            return "improved"
        if candidate.score < self.best.score:
            return "degraded"
        return "unchanged"

    def _persist_record(self, candidate: CandidateResult) -> None:
        """Persist candidate summary using the configured sink."""
        record = {
            "params_id": candidate.params_id,
            "objective": self.objective.config.name,
            "target_metric": self.objective.config.target_metric,
            "target_value": candidate.objective_value,
            "score": candidate.score,
            "status": candidate.status,
            "start_date": candidate.start_date.isoformat(),
            "end_date": candidate.end_date.isoformat(),
            "metrics": candidate.metrics,
            "engine_args": candidate.engine_args,
            "execution_overrides": candidate.execution_overrides,
            "drawdown_limit": getattr(self.objective.config, "max_drawdown_limit", None),
        }
        # Include tracking_error_summary if available in metrics
        if "tracking_error_summary" in candidate.metrics:
            record["tracking_error_summary"] = candidate.metrics["tracking_error_summary"]
        self.records.append(record)
        if self.persist_fn:
            self.persist_fn(record)
        else:
            logger.info("Campaign candidate evaluated", extra=record)

