"""Recommendation endpoints."""
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.models.recommendation import RecommendationResponse, SignalPerformanceResponse
from app.services.recommendation_service import RecommendationService

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
            disclaimer=data["disclaimer"],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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

