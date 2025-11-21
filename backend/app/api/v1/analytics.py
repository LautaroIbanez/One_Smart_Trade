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
from app.utils.cache import get_cached, set_cached
from app.utils.async_timeout import with_timeout, ProcessingResponse
import time


router = APIRouter()


@router.get("/livelihood/latest-run-id")
async def get_latest_run_id() -> dict[str, Any]:
    """Get the latest run_id from completed campaigns (from PerformancePeriodicORM or StrategyChampionORM)."""
    with SessionLocal() as db:
        from app.db.models import StrategyChampionORM
        from sqlalchemy import desc
        
        # Try to get run_id from latest champion
        champion = db.execute(
            select(StrategyChampionORM)
            .where(StrategyChampionORM.is_active == True)
            .order_by(desc(StrategyChampionORM.promoted_at))
            .limit(1)
        ).scalars().first()
        
        if champion and champion.metrics:
            # Try to extract run_id from champion metrics
            run_id = champion.metrics.get("run_id") or champion.metrics.get("params_id")
            if run_id:
                return {"run_id": str(run_id), "source": "champion"}
        
        # Fallback: get latest run_id from PerformancePeriodicORM
        latest_periodic = db.execute(
            select(PerformancePeriodicORM.run_id)
            .distinct()
            .order_by(desc(PerformancePeriodicORM.created_at))
            .limit(1)
        ).scalars().first()
        
        if latest_periodic:
            return {"run_id": str(latest_periodic), "source": "periodic_metrics"}
        
        return {"run_id": None, "source": None}


class LivelihoodRequest(BaseModel):
    monthly_returns: conlist(float, min_length=3) = Field(..., description="Monthly return series as decimals, e.g., 0.02 for +2%")
    expenses_target: float = Field(0.0, ge=0.0, description="Target monthly expenses in USD")
    trials: int = Field(10_000, ge=1000, le=100_000)
    horizon_months: int = Field(36, ge=6, le=120)
    ruin_threshold: float = Field(0.7, gt=0.0, lt=1.0, description="Equity fraction defining ruin (e.g., 0.7 = -30%)")


class LivelihoodResponse(BaseModel):
    survival: dict[str, float]
    scenarios: list[dict[str, Any]]
    periodic_metrics: dict[str, Any] | None = None
    income_curves: dict[str, Any] | None = None

class FeedbackRequest(BaseModel):
    user_id: str | None = None
    run_id: str | None = None
    rating: int = Field(..., ge=1, le=5)
    comments: str | None = None
    context: dict[str, Any] | None = None


@router.post("/livelihood", response_model=LivelihoodResponse)
async def compute_livelihood(payload: LivelihoodRequest) -> LivelihoodResponse:
    """
    Compute survival analysis and account scenarios from provided monthly return series.
    
    Results are cached for 5 minutes to avoid recomputing expensive Monte Carlo simulations.
    """
    from app.core.logging import logger
    from app.observability.metrics import ENDPOINT_RESPONSE_TIME
    
    start_time = time.time()
    
    # Check cache (cache key based on input parameters)
    cache_key_args = (
        tuple(payload.monthly_returns),
        payload.expenses_target,
        payload.trials,
        payload.horizon_months,
        payload.ruin_threshold,
    )
    cached_result = get_cached("analytics_livelihood", ttl_seconds=300.0, *cache_key_args)
    if cached_result:
        duration = time.time() - start_time
        ENDPOINT_RESPONSE_TIME.labels(endpoint="/analytics/livelihood", status="cached").observe(duration)
        return LivelihoodResponse(**cached_result)
    
    # Execute with timeout (20 seconds max)
    async def compute():
        series = pd.Series(payload.monthly_returns)
        sim = SurvivalSimulator(trials=payload.trials, horizon_months=payload.horizon_months, ruin_threshold=payload.ruin_threshold)
        survival = sim.monte_carlo(series)
        scenarios = LivelihoodReport().build(series, expenses_target=payload.expenses_target)
        return {
            "survival": survival,
            "scenarios": [s.__dict__ for s in scenarios],
        }
    
    result = await with_timeout(compute, timeout_seconds=20.0, timeout_message="Livelihood computation timed out")
    if result is None:
        # Return processing response if timeout
        processing = ProcessingResponse(
            operation_id=f"livelihood_{int(time.time())}",
            message="Computation is taking longer than expected. Please retry in a few moments.",
            estimated_seconds=30.0,
        )
        raise HTTPException(status_code=202, detail=processing.to_dict())
    
    # Cache result
    set_cached("analytics_livelihood", result, ttl_seconds=300.0, *cache_key_args)
    
    duration = time.time() - start_time
    ENDPOINT_RESPONSE_TIME.labels(endpoint="/analytics/livelihood", status="success").observe(duration)
    
    if duration > 10.0:
        logger.warning(f"Livelihood computation took {duration:.2f}s", extra={"duration": duration})
    
    return LivelihoodResponse(**result)


@router.get("/livelihood/{run_id}", response_model=LivelihoodResponse)
async def compute_livelihood_from_run(
    run_id: str,
    expenses_target: float = Query(settings.DEFAULT_EXPENSES_TARGET_USD, ge=0.0),
    trials: int = Query(10_000, ge=1000, le=100_000),
    horizon_months: int = Query(36, ge=6, le=120),
    ruin_threshold: float = Query(0.7, gt=0.0, lt=1.0),
) -> LivelihoodResponse:
    """Compute survival and scenarios using stored monthly performance for a given run_id."""
    from app.analytics.periodic_metrics import PeriodicMetricsBuilder
    from app.backtesting.persistence import BacktestResultRepository
    from app.core.logging import logger
    
    with SessionLocal() as db:
        returns = _load_monthly_returns(db, run_id)
        if returns.empty:
            raise HTTPException(status_code=404, detail=f"No monthly returns found for run_id={run_id}")
    
    # Calculate survival and scenarios
    sim = SurvivalSimulator(trials=trials, horizon_months=horizon_months, ruin_threshold=ruin_threshold)
    survival = sim.monte_carlo(returns)
    scenarios = LivelihoodReport().build(returns, expenses_target=expenses_target)
    
    # Build periodic metrics and income curves
    periodic_metrics_data = None
    income_curves_data = None
    
    try:
        # Try to load equity curves from backtest result
        repo = BacktestResultRepository()
        backtest_result = repo.load(run_id)
        
        if backtest_result and backtest_result.equity_curve_theoretical and backtest_result.equity_curve_realistic:
            # Build equity curves as pandas Series
            theoretical_equity = pd.Series(
                [p["equity"] for p in backtest_result.equity_curve_theoretical],
                index=pd.to_datetime([p["timestamp"] for p in backtest_result.equity_curve_theoretical])
            )
            realistic_equity = pd.Series(
                [p["equity"] for p in backtest_result.equity_curve_realistic],
                index=pd.to_datetime([p["timestamp"] for p in backtest_result.equity_curve_realistic])
            )
            
            # Build periodic metrics from equity curves
            builder = PeriodicMetricsBuilder()
            periodic_metrics = builder.build(theoretical_equity)
            
            # Extract max_loss_streak and max_loss_duration from monthly metrics
            monthly_metrics = next((m for m in periodic_metrics if m.horizon == "monthly"), None)
            quarterly_metrics = next((m for m in periodic_metrics if m.horizon == "quarterly"), None)
            
            periodic_metrics_data = {
                "monthly": {
                    "stats": monthly_metrics.stats if monthly_metrics else {},
                    "max_loss_streak": monthly_metrics.stats.get("max_loss_streak", 0) if monthly_metrics else 0,
                    "max_loss_duration": monthly_metrics.stats.get("max_loss_duration", 0) if monthly_metrics else 0,
                },
                "quarterly": {
                    "stats": quarterly_metrics.stats if quarterly_metrics else {},
                    "max_loss_streak": quarterly_metrics.stats.get("max_loss_streak", 0) if quarterly_metrics else 0,
                    "max_loss_duration": quarterly_metrics.stats.get("max_loss_duration", 0) if quarterly_metrics else 0,
                },
            }
            
            # Build income curves (theoretical vs viable) for each capital scenario
            income_curves_data = {}
            for capital in (1_000, 4_000, 10_000, 50_000):
                # Calculate theoretical income (from theoretical equity)
                theoretical_returns = theoretical_equity.pct_change().dropna()
                theoretical_monthly = (1 + theoretical_returns).resample("M").prod() - 1
                theoretical_income = theoretical_monthly * capital
                
                # Calculate viable income (from realistic equity)
                realistic_returns = realistic_equity.pct_change().dropna()
                realistic_monthly = (1 + realistic_returns).resample("M").prod() - 1
                viable_income = realistic_monthly * capital
                
                # Align indices
                common_index = theoretical_income.index.intersection(viable_income.index)
                theoretical_income_aligned = theoretical_income.reindex(common_index).fillna(0)
                viable_income_aligned = viable_income.reindex(common_index).fillna(0)
                
                income_curves_data[str(capital)] = {
                    "theoretical": [
                        {"timestamp": ts.isoformat(), "income": float(val)}
                        for ts, val in zip(common_index, theoretical_income_aligned.values)
                    ],
                    "viable": [
                        {"timestamp": ts.isoformat(), "income": float(val)}
                        for ts, val in zip(common_index, viable_income_aligned.values)
                    ],
                }
        else:
            # Fallback: build periodic metrics from monthly returns only
            # Create a synthetic equity curve from returns
            equity_curve = (1 + returns).cumprod() * 10000  # Start with 10k
            builder = PeriodicMetricsBuilder()
            periodic_metrics = builder.build(equity_curve)
            
            monthly_metrics = next((m for m in periodic_metrics if m.horizon == "monthly"), None)
            quarterly_metrics = next((m for m in periodic_metrics if m.horizon == "quarterly"), None)
            
            periodic_metrics_data = {
                "monthly": {
                    "stats": monthly_metrics.stats if monthly_metrics else {},
                    "max_loss_streak": monthly_metrics.stats.get("max_loss_streak", 0) if monthly_metrics else 0,
                    "max_loss_duration": monthly_metrics.stats.get("max_loss_duration", 0) if monthly_metrics else 0,
                },
                "quarterly": {
                    "stats": quarterly_metrics.stats if quarterly_metrics else {},
                    "max_loss_streak": quarterly_metrics.stats.get("max_loss_streak", 0) if quarterly_metrics else 0,
                    "max_loss_duration": quarterly_metrics.stats.get("max_loss_duration", 0) if quarterly_metrics else 0,
                },
            }
    except Exception as e:
        logger.warning(f"Failed to build periodic metrics or income curves: {e}", exc_info=True)
    
    return LivelihoodResponse(
        survival=survival,
        scenarios=[s.__dict__ for s in scenarios],
        periodic_metrics=periodic_metrics_data,
        income_curves=income_curves_data,
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


