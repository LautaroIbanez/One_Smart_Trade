"""Market data endpoints."""
from fastapi import APIRouter, HTTPException
from typing import Literal
from app.services.market_service import MarketService

router = APIRouter()
market_service = MarketService()

Interval = Literal["15m", "30m", "1h", "4h", "1d", "1w"]


@router.get("/{interval}")
async def get_market_data(interval: Interval):
    """Get market data for a specific interval."""
    try:
        data = await market_service.get_market_data(interval)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

