"""Campaign optimizer tracking objective-driven improvements."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.backtesting.engine import BacktestEngine
from app.backtesting.metrics import calculate_metrics
from app.backtesting.objectives import CalmarUnderDrawdown, Objective
from app.core.logging import logger

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
    ) -> None:
        self.objective = objective or CalmarUnderDrawdown()
        self.persist_fn = persist_fn
        self.best: CandidateResult | None = None
        self.records: list[dict[str, Any]] = []
        self.max_ruin_probability = max_ruin_probability
        self.max_negative_month_prob = max_negative_month_prob

    def evaluate(
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

            try:
                engine = BacktestEngine(**execution_overrides)
                backtest_result = engine.run_backtest(start, end, **engine_args)
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
        self.records.append(record)
        if self.persist_fn:
            self.persist_fn(record)
        else:
            logger.info("Campaign candidate evaluated", extra=record)

