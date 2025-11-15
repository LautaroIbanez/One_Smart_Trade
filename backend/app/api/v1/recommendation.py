"""Recommendation endpoints."""
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.core.database import SessionLocal
from app.core.logging import logger
from app.db.models import RecommendationORM
from app.models.recommendation import RecommendationResponse, SignalPerformanceResponse
from app.services.recommendation_service import RecommendationService
from app.backtesting.risk_sizing import RiskSizer
from app.utils.worm_storage import WormRepository
from sqlalchemy import select

router = APIRouter()
recommendation_service = RecommendationService()


@router.get("/today", response_model=RecommendationResponse)
async def get_today_recommendation():
    """
    Get today's trading recommendation.

    Returns signal, entry range, SL/TP, confidence, indicators, risk metrics, factors, and analysis.
    """
    try:
        data = await recommendation_service.get_today_recommendation()
        if not data:
            raise HTTPException(status_code=404, detail="No recommendation available for today")
        if data.get("status") == "invalid":
            raise HTTPException(status_code=422, detail=data.get("reason", "Invalid recommendation"))
        return RecommendationResponse(
            signal=data["signal"],
            entry_range=data["entry_range"],
            stop_loss_take_profit=data["stop_loss_take_profit"],
            confidence=data["confidence"],
            current_price=data["current_price"],
            analysis=data["analysis"],
            indicators=data["indicators"],
            risk_metrics=data["risk_metrics"],
            factors=data.get("factors", {}),
            signal_breakdown=data.get("signal_breakdown", {}),
            timestamp=data["timestamp"],
            status=data.get("status", "closed"),
            opened_at=data.get("opened_at"),
            closed_at=data.get("closed_at"),
            exit_reason=data.get("exit_reason"),
            exit_price=data.get("exit_price"),
            exit_price_pct=data.get("exit_price_pct"),
            recommended_risk_fraction=data.get("recommended_risk_fraction", 0.01),
            disclaimer=data["disclaimer"],
            suggested_sizing=data.get("suggested_sizing"),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{recommendation_id}/snapshot")
async def get_recommendation_snapshot(recommendation_id: int):
    """
    Get immutable snapshot and verification hashes for a recommendation.

    Returns the full snapshot with code_commit, dataset_hash, and params_hash
    for independent verification.
    """
    with SessionLocal() as db:
        stmt = select(RecommendationORM).where(RecommendationORM.id == recommendation_id)
        rec = db.execute(stmt).scalars().first()
        if not rec:
            raise HTTPException(status_code=404, detail="Recommendation not found")

        # Get snapshot from WORM storage if available
        worm_repo = WormRepository()
        worm_snapshot = None
        if rec.snapshot_json and rec.snapshot_json.get("worm_uuid"):
            try:
                worm_snapshot = worm_repo.read_snapshot(uuid=rec.snapshot_json["worm_uuid"])
            except Exception as e:
                logger.warning(f"Failed to read WORM snapshot: {e}", exc_info=True)

        # Prepare response
        snapshot_data = {
            "recommendation_id": rec.id,
            "date": rec.date,
            "timestamp": rec.created_at.isoformat(),
            "code_commit": rec.code_commit,
            "dataset_hash": rec.dataset_version,
            "params_hash": rec.params_digest,
            "snapshot_json": rec.snapshot_json,
        }

        if worm_snapshot:
            snapshot_data["worm_snapshot"] = {
                "uuid": worm_snapshot.get("uuid"),
                "path": rec.snapshot_json.get("worm_path"),
                "hash": rec.snapshot_json.get("worm_hash"),
                "timestamp": worm_snapshot.get("timestamp"),
                "payload": worm_snapshot.get("payload"),
                "metadata": worm_snapshot.get("metadata"),
            }

        return snapshot_data


@router.get("/performance", response_model=SignalPerformanceResponse)
async def get_signal_performance(lookahead_days: int = 5, limit: int = 90):
    try:
        data = await recommendation_service.get_signal_performance(
            lookahead_days=lookahead_days,
            limit=limit,
        )
        return SignalPerformanceResponse(**data)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/history")
async def get_recommendation_history(limit: Optional[int] = 10):
    """
    Get recent recommendation history.

    Returns list of past recommendations with all fields including analysis.
    """
    try:
        if limit and (limit < 1 or limit > 100):
            raise HTTPException(status_code=400, detail="Limit must be between 1 and 100")
        history = await recommendation_service.get_recommendation_history(limit=limit or 10)
        return {"recommendations": history, "count": len(history)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

