"""Recommendation endpoints."""
from fastapi import APIRouter, HTTPException
from datetime import datetime
from typing import Optional
from app.services.recommendation_service import RecommendationService

router = APIRouter()
recommendation_service = RecommendationService()


@router.get("/today")
async def get_today_recommendation():
    """Get today's trading recommendation."""
    try:
        recommendation = await recommendation_service.get_today_recommendation()
        if not recommendation:
            raise HTTPException(status_code=404, detail="No recommendation available for today")
        return recommendation
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_recommendation_history(limit: Optional[int] = 10):
    """Get recent recommendation history."""
    try:
        history = await recommendation_service.get_recommendation_history(limit=limit)
        return {"recommendations": history, "count": len(history)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

