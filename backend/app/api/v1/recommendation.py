"""Recommendation endpoints."""
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.models.recommendation import Recommendation
from app.services.recommendation_service import RecommendationService

router = APIRouter()
recommendation_service = RecommendationService()


@router.get("/today", response_model=Recommendation)
async def get_today_recommendation():
    """
    Get today's trading recommendation.

    Returns signal, entry range, SL/TP, confidence, indicators, risk metrics, factors, and analysis.
    """
    try:
        recommendation = await recommendation_service.get_today_recommendation()
        if not recommendation:
            raise HTTPException(status_code=404, detail="No recommendation available for today")
        return recommendation
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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

