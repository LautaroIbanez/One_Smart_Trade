from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, conlist
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.livelihood_report import LivelihoodReport
from app.analytics.ruin import SurvivalSimulator
from app.core.database import SessionLocal
from app.db.models import PerformancePeriodicORM, PeriodicHorizon
from app.services.worm_storage import store_artifact
from app.core.config import settings


router = APIRouter()


class LivelihoodRequest(BaseModel):
    monthly_returns: conlist(float, min_items=3) = Field(..., description="Monthly return series as decimals, e.g., 0.02 for +2%")
    expenses_target: float = Field(0.0, ge=0.0, description="Target monthly expenses in USD")
    trials: int = Field(10_000, ge=1000, le=100_000)
    horizon_months: int = Field(36, ge=6, le=120)
    ruin_threshold: float = Field(0.7, gt=0.0, lt=1.0, description="Equity fraction defining ruin (e.g., 0.7 = -30%)")


class LivelihoodResponse(BaseModel):
    survival: dict[str, float]
    scenarios: list[dict[str, Any]]

class FeedbackRequest(BaseModel):
    user_id: str | None = None
    run_id: str | None = None
    rating: int = Field(..., ge=1, le=5)
    comments: str | None = None
    context: dict[str, Any] | None = None


@router.post("/livelihood", response_model=LivelihoodResponse)
async def compute_livelihood(payload: LivelihoodRequest) -> LivelihoodResponse:
    """Compute survival analysis and account scenarios from provided monthly return series."""
    series = pd.Series(payload.monthly_returns)
    sim = SurvivalSimulator(trials=payload.trials, horizon_months=payload.horizon_months, ruin_threshold=payload.ruin_threshold)
    survival = sim.monte_carlo(series)
    scenarios = LivelihoodReport().build(series, expenses_target=payload.expenses_target)
    return LivelihoodResponse(
        survival=survival,
        scenarios=[s.__dict__ for s in scenarios],
    )


@router.get("/livelihood/{run_id}", response_model=LivelihoodResponse)
async def compute_livelihood_from_run(
    run_id: str,
    expenses_target: float = Query(settings.DEFAULT_EXPENSES_TARGET_USD, ge=0.0),
    trials: int = Query(10_000, ge=1000, le=100_000),
    horizon_months: int = Query(36, ge=6, le=120),
    ruin_threshold: float = Query(0.7, gt=0.0, lt=1.0),
) -> LivelihoodResponse:
    """Compute survival and scenarios using stored monthly performance for a given run_id."""
    with SessionLocal() as db:
        returns = _load_monthly_returns(db, run_id)
        if returns.empty:
            raise HTTPException(status_code=404, detail=f"No monthly returns found for run_id={run_id}")
    sim = SurvivalSimulator(trials=trials, horizon_months=horizon_months, ruin_threshold=ruin_threshold)
    survival = sim.monte_carlo(returns)
    scenarios = LivelihoodReport().build(returns, expenses_target=expenses_target)
    return LivelihoodResponse(
        survival=survival,
        scenarios=[s.__dict__ for s in scenarios],
    )


@router.get("/livelihood/{run_id}/export")
async def export_livelihood_run(
    run_id: str,
    format: str = Query("csv", regex="^(csv|json)$"),
    expenses_target: float = Query(0.0, ge=0.0),
    trials: int = Query(10_000, ge=1000, le=100_000),
    horizon_months: int = Query(36, ge=6, le=120),
    ruin_threshold: float = Query(0.7, gt=0.0, lt=1.0),
) -> dict[str, str | int]:
    """Export livelihood analysis for a run to WORM storage and return hashes."""
    with SessionLocal() as db:
        returns = _load_monthly_returns(db, run_id)
        if returns.empty:
            raise HTTPException(status_code=404, detail=f"No monthly returns found for run_id={run_id}")
    sim = SurvivalSimulator(trials=trials, horizon_months=horizon_months, ruin_threshold=ruin_threshold)
    survival = sim.monte_carlo(returns)
    scenarios = [s.__dict__ for s in LivelihoodReport().build(returns, expenses_target=expenses_target)]
    if format == "csv":
        import io
        import csv
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["capital", "monthly_income_p10", "monthly_income_p50", "monthly_income_p90", "negative_month_prob", "sustainable_capital"])
        for s in scenarios:
            writer.writerow([s["capital"], s["monthly_income_p10"], s["monthly_income_p50"], s["monthly_income_p90"], s["negative_month_prob"], s["sustainable_capital"]])
        writer.writerow([])
        writer.writerow(["metric", "value"])
        for k, v in survival.items():
            writer.writerow([k, v])
        content = buf.getvalue().encode("utf-8")
        artifact = store_artifact(content, prefix=f"livelihood_{run_id}", ext="csv")
    else:
        import json
        payload = {"run_id": run_id, "expenses_target": expenses_target, "survival": survival, "scenarios": scenarios}
        content = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        artifact = store_artifact(content, prefix=f"livelihood_{run_id}", ext="json")
    return {
        "path": str(artifact.path),
        "md5": artifact.md5,
        "sha256": artifact.sha256,
        "size": artifact.size,
        "retention_days": settings.WORM_RETENTION_DAYS,
        "hash_ttl_days": settings.HASH_TTL_DAYS,
        "download_roles_allowed": settings.EXPORT_ROLES_ALLOWED,
    }


@router.post("/feedback")
async def submit_feedback(payload: FeedbackRequest) -> dict[str, str | int]:
    """Submit beta feedback; store as WORM JSON with hashes for auditability."""
    import json
    from datetime import datetime
    content = {
        "timestamp": datetime.utcnow().isoformat(),
        "user_id": payload.user_id,
        "run_id": payload.run_id,
        "rating": payload.rating,
        "comments": payload.comments,
        "context": payload.context or {},
    }
    data = json.dumps(content, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    artifact = store_artifact(data, prefix="livelihood_feedback", ext="json")
    return {"path": str(artifact.path), "md5": artifact.md5, "sha256": artifact.sha256, "size": artifact.size}


def _load_monthly_returns(db: Session, run_id: str) -> pd.Series:
    stmt = (
        select(PerformancePeriodicORM)
        .where(PerformancePeriodicORM.run_id == run_id)
        .where(PerformancePeriodicORM.horizon == PeriodicHorizon.monthly)
        .order_by(PerformancePeriodicORM.period.asc())
    )
    rows = list(db.execute(stmt).scalars().all())
    if not rows:
        return pd.Series(dtype=float)
    # Use mean column as monthly return for now (persisted by generate_periodic_metrics script)
    periods = [r.period for r in rows]
    values = [r.mean for r in rows]
    return pd.Series(values, index=pd.to_datetime([p + "-01" for p in periods], errors="coerce"))


