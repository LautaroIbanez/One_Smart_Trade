from __future__ import annotations

from typing import Iterable

import pandas as pd
from sqlalchemy import select

from app.analytics.livelihood_report import LivelihoodReport
from app.analytics.ruin import SurvivalSimulator
from app.core.database import SessionLocal
from app.core.logging import logger
from app.db.models import PerformancePeriodicORM, PeriodicHorizon


def run_for_runs(run_ids: Iterable[str], *, trials: int = 10_000, horizon_months: int = 36, ruin_threshold: float = 0.7) -> None:
    with SessionLocal() as db:
        for run_id in run_ids:
            series = _load_monthly_returns(db, run_id)
            if series.empty:
                logger.info("Skipping run_id with no monthly data", extra={"run_id": run_id})
                continue
            sim = SurvivalSimulator(trials=trials, horizon_months=horizon_months, ruin_threshold=ruin_threshold)
            survival = sim.monte_carlo(series)
            scenarios = LivelihoodReport().build(series, expenses_target=0.0)
            logger.info(
                "Livelihood recomputed",
                extra={"run_id": run_id, "survival": survival, "scenario_p50": scenarios[0].monthly_income_p50 if scenarios else None},
            )


def _load_monthly_returns(db, run_id: str) -> pd.Series:
    stmt = (
        select(PerformancePeriodicORM)
        .where(PerformancePeriodicORM.run_id == run_id)
        .where(PerformancePeriodicORM.horizon == PeriodicHorizon.monthly)
        .order_by(PerformancePeriodicORM.period.asc())
    )
    rows = list(db.execute(stmt).scalars().all())
    if not rows:
        return pd.Series(dtype=float)
    periods = [r.period for r in rows]
    values = [r.mean for r in rows]
    return pd.Series(values, index=pd.to_datetime([p + "-01" for p in periods], errors="coerce"))


if __name__ == "__main__":
    # Example: recompute for the most recent N run_ids
    with SessionLocal() as db:
        q = (
            select(PerformancePeriodicORM.run_id)
            .where(PerformancePeriodicORM.horizon == PeriodicHorizon.monthly)
            .group_by(PerformancePeriodicORM.run_id)
            .limit(50)
        )
        run_ids = [row[0] for row in db.execute(q).all()]
    run_for_runs(run_ids)


