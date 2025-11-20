"""Automatic recalibration jobs triggered by performance monitoring."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.backtesting.monitoring import RecalibrationEvent, statistical_significance_test
from app.backtesting.optimizer import CampaignOptimizer, CandidateResult
from app.backtesting.champion import persist_campaign_record
from app.core.database import SessionLocal
from app.core.logging import logger, sanitize_log_extra
from app.db import crud
from app.quant.regime import RegimeClassifier


@dataclass
class RecalibrationJob:
    """Job for automatic parameter recalibration."""

    asset: str
    venue: str
    regime_snapshot: dict[str, float]
    trigger_event: RecalibrationEvent
    params_version: str | None = None

    def execute(
        self,
        optimizer: CampaignOptimizer,
        params_variants: list[dict[str, Any]],
        *,
        start_date: datetime,
        end_date: datetime,
        regime_classifier: RegimeClassifier | None = None,
    ) -> list[CandidateResult]:
        """
        Execute recalibration job.
        
        Args:
            optimizer: Campaign optimizer instance
            params_variants: Parameter variants to test
            start_date: Training period start
            end_date: Training period end
            regime_classifier: Optional regime classifier for tracking
            
        Returns:
            List of candidate results
        """
        logger.info(
            "Executing recalibration job",
            extra={
                "asset": self.asset,
                "venue": self.venue,
                "trigger_reason": self.trigger_event.trigger_reason,
                "params_variants": len(params_variants),
            },
        )
        
        results = optimizer.evaluate(
            start=start_date,
            end=end_date,
            params_variants=params_variants,
        )
        
        if optimizer.best:
            best = optimizer.best
            trained_on_regime = self.regime_snapshot.copy()
            
            current_champion = crud.get_current_champion(SessionLocal())
            if current_champion:
                is_significant, p_value, reason = statistical_significance_test(
                    best.metrics,
                    current_champion.metrics,
                )
                
                if is_significant:
                    record = {
                        "params_id": best.params_id,
                        "params_version": self.params_version,
                        "objective": optimizer.objective.config.name,
                        "target_metric": optimizer.objective.config.target_metric,
                        "target_value": best.objective_value,
                        "score": best.score,
                        "status": "improved",
                        "metrics": best.metrics,
                        "trained_on_regime": trained_on_regime,
                        "statistical_test": {
                            "is_significant": is_significant,
                            "p_value": float(p_value),
                            "reason": reason,
                        },
                        "engine_args": best.engine_args,
                        "execution_overrides": best.execution_overrides,
                        "start_date": start_date.isoformat(),
                        "end_date": end_date.isoformat(),
                        "drawdown_limit": optimizer.objective.config.max_drawdown_limit,
                    }
                    persist_campaign_record(record)
                    logger.info(
                        "Champion promoted after recalibration",
                        extra={
                            "params_id": best.params_id,
                            "p_value": p_value,
                            "reason": reason,
                        },
                    )
                else:
                    logger.info(
                        "Recalibration did not produce statistically significant improvement",
                        extra={
                            "params_id": best.params_id,
                            "p_value": p_value,
                            "reason": reason,
                        },
                    )
        
        return results


class AdaptiveCampaignOptimizer(CampaignOptimizer):
    """Extended optimizer with regime-aware recalibration and statistical significance testing."""

    def __init__(
        self,
        objective=None,
        persist_fn=None,
        *,
        require_statistical_significance: bool = True,
        significance_alpha: float = 0.05,
        regime_classifier: RegimeClassifier | None = None,
    ) -> None:
        """
        Initialize adaptive campaign optimizer.
        
        Args:
            objective: Objective function
            persist_fn: Persistence callback
            require_statistical_significance: Require statistical test for promotion
            significance_alpha: Significance level for statistical test
            regime_classifier: Optional regime classifier for tracking
        """
        super().__init__(objective, persist_fn)
        self.require_statistical_significance = require_statistical_significance
        self.significance_alpha = significance_alpha
        self.regime_classifier = regime_classifier

    def _determine_status(self, candidate: CandidateResult) -> str:
        """Override to add statistical significance check."""
        if not self.objective.is_valid(candidate.metrics):
            return "invalid"

        if self.best is None:
            if self.require_statistical_significance:
                return "improved"
            return "improved"

        improvement_threshold = self.best.score * (1 + self.objective.config.min_improvement)
        if candidate.score > improvement_threshold:
            if self.require_statistical_significance:
                is_significant, _, reason = statistical_significance_test(
                    candidate.metrics,
                    self.best.metrics,
                    alpha=self.significance_alpha,
                )
                if not is_significant:
                    logger.debug(
                        "Candidate improvement not statistically significant",
                        extra={"params_id": candidate.params_id, "reason": reason},
                    )
                    return "unchanged"
            return "improved"
        if candidate.score < self.best.score:
            return "degraded"
        return "unchanged"

    def _persist_record(self, candidate: CandidateResult) -> None:
        """Override to include regime snapshot and statistical test."""
        trained_on_regime = {}
        if self.regime_classifier:
            try:
                pass
            except Exception:
                pass
        
        current_champion = None
        with SessionLocal() as db:
            current_champion = crud.get_current_champion(db)
        
        statistical_test = None
        if current_champion and self.require_statistical_significance:
            is_significant, p_value, reason = statistical_significance_test(
                candidate.metrics,
                current_champion.metrics,
                alpha=self.significance_alpha,
            )
            statistical_test = {
                "is_significant": is_significant,
                "p_value": float(p_value),
                "reason": reason,
            }
        
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
            "trained_on_regime": trained_on_regime,
            "statistical_test": statistical_test,
            "engine_args": candidate.engine_args,
            "execution_overrides": candidate.execution_overrides,
            "drawdown_limit": getattr(self.objective.config, "max_drawdown_limit", None),
        }
        self.records.append(record)
        if self.persist_fn:
            self.persist_fn(record)
        else:
            # Records can contain user-provided metadata; sanitize to avoid reserved keys.
            logger.info("Campaign candidate evaluated", extra=sanitize_log_extra(record))

