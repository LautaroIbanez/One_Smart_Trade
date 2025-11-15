"""Validation pipeline coordinating training, validation, and out-of-sample checks."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from app.backtesting.engine import BacktestEngine
from app.backtesting.champion import persist_campaign_record
from app.backtesting.time_split import CurationDataLoader, TimeSplitPipeline
from app.backtesting.objectives import CalmarUnderDrawdown, Objective
from app.backtesting.optimizer import CampaignOptimizer, CandidateResult, PersistRecordFn
from app.core.logging import logger
from app.data.curation import DataCuration


@dataclass(frozen=True)
class WalkSegment:
    """Represents a contiguous walk-forward evaluation window."""

    start: datetime
    end: datetime


class ValidationPipeline:
    """Run a multi-stage validation process for trading strategies."""

    def __init__(
        self,
        objective: Objective | None = None,
        *,
        persist_fn: PersistRecordFn | None = None,
    ) -> None:
        self.objective = objective or CalmarUnderDrawdown()
        self.persist_fn = persist_fn or persist_campaign_record
        self._curation = DataCuration()
        self._loader = CurationDataLoader(self._curation)

    def run(
        self,
        start: datetime,
        end: datetime,
        *,
        train_span_days: int = 365,
        test_span_days: int = 90,
        walk_window_days: int = 180,
        oos_span_days: int | None = None,
        param_grid: Iterable[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Execute the full validation pipeline."""
        if start >= end:
            raise ValueError("Start date must be earlier than end date.")
        if train_span_days < 30:
            raise ValueError("Training span must be at least 30 days.")
        if test_span_days < 30:
            raise ValueError("Test span must be at least 30 days.")
        if walk_window_days < 30:
            raise ValueError("Walk-forward window must be at least 30 days.")

        oos_span_days = oos_span_days or test_span_days
        if oos_span_days < 30:
            raise ValueError("Out-of-sample span must be at least 30 days.")

        splitter = TimeSplitPipeline(self._loader, walk_days=walk_window_days)
        splits = splitter.split(
            start,
            end,
            train_days=train_span_days,
            val_days=test_span_days,
            test_days=oos_span_days,
        )

        train_window = splits["train"][0]
        validation_window = splits["validation"][0]
        test_window = splits["test"][0]
        walk_windows = splits["walk_forward"]

        for window in (train_window, validation_window, test_window, *walk_windows):
            frame = splitter.materialize(window)
            if frame.empty:
                raise ValueError(f"No data available for window {window.role} {window.start} → {window.end}")

        optimizer = CampaignOptimizer(objective=self.objective, persist_fn=self.persist_fn)

        train_variants = list(param_grid or self._generate_param_grid())
        if not train_variants:
            raise ValueError("Parameter grid is empty; cannot run training stage.")

        train_start_dt, train_end_dt = train_window.as_datetime_tuple()
        logger.info(
            "Starting training stage",
            extra={
                "start": train_start_dt.isoformat(),
                "end": train_end_dt.isoformat(),
                "variants": len(train_variants),
            },
        )
        train_results = optimizer.evaluate(start=train_start_dt, end=train_end_dt, params_variants=train_variants)

        if optimizer.best is None:
            raise RuntimeError("Training stage did not produce a valid champion candidate.")

        best_variant = self._prepare_variant(optimizer.best, extra_engine_args={"initial_capital": 10000.0})

        val_start_dt, val_end_dt = validation_window.as_datetime_tuple()
        validation_results: list[CandidateResult] = []
        if val_start_dt <= val_end_dt:
            logger.info(
                "Starting validation stage",
                extra={"start": val_start_dt.isoformat(), "end": val_end_dt.isoformat()},
            )
            validation_results = optimizer.evaluate(
                start=val_start_dt,
                end=val_end_dt,
                params_variants=[best_variant],
            )

        walk_results: list[CandidateResult] = []
        walk_segments: list[WalkSegment] = []
        if walk_windows:
            walk_segments = [
                WalkSegment(start=window.start.to_pydatetime(), end=window.end.to_pydatetime())
                for window in walk_windows
            ]
            logger.info(
                "Starting walk-forward stage",
                extra={
                    "segments": len(walk_segments),
                    "start": walk_segments[0].start.isoformat(),
                    "end": walk_segments[-1].end.isoformat(),
                },
            )
            for window in walk_windows:
                walk_results.extend(
                    optimizer.evaluate(
                        start=window.start.to_pydatetime(),
                        end=window.end.to_pydatetime(),
                        params_variants=[best_variant],
                    )
                )

        oos_result: list[CandidateResult] = []
        test_start_dt, test_end_dt = test_window.as_datetime_tuple()
        if test_start_dt <= test_end_dt:
            logger.info(
                "Starting out-of-sample stage",
                extra={"start": test_start_dt.isoformat(), "end": test_end_dt.isoformat()},
            )
            oos_result = optimizer.evaluate(
                start=test_start_dt,
                end=test_end_dt,
                params_variants=[best_variant],
            )

        return {
            "train": train_results,
            "validation": validation_results,
            "walk_forward": walk_results,
            "walk_segments": walk_segments,
            "out_of_sample": oos_result,
            "champion": optimizer.best,
            "records": optimizer.records,
        }

    def _generate_param_grid(self) -> Iterable[dict[str, Any]]:
        """Provide a default parameter grid across risk settings."""
        position_sizes = [0.5, 0.75, 1.0]
        commissions = [BacktestEngine.COMMISSION_RATE, BacktestEngine.COMMISSION_RATE * 1.5]
        variants: list[dict[str, Any]] = []
        for idx, (size, commission) in enumerate(
            ((size, commission) for size in position_sizes for commission in commissions),
            start=1,
        ):
            variants.append(
                {
                    "id": f"variant_{idx:02d}",
                    "engine_args": {"position_size_pct": size},
                    "execution_overrides": {"commission": commission},
                }
            )
        return variants

    def _prepare_variant(
        self,
        candidate: CandidateResult,
        extra_engine_args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Reconstruct the variant definition from the champion candidate."""
        variant: dict[str, Any] = {"id": candidate.params_id}
        if candidate.execution_overrides:
            variant["execution_overrides"] = dict(candidate.execution_overrides)
        engine_args = dict(candidate.engine_args)
        if extra_engine_args:
            engine_args.update(extra_engine_args)
        if engine_args:
            variant["engine_args"] = engine_args
        return variant

