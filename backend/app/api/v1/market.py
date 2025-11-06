"""Market data endpoints."""
from fastapi import APIRouter, HTTPException
from typing import Literal
from app.services.market_service import MarketService

router = APIRouter()
market_service = MarketService()

Interval = Literal["15m", "30m", "1h", "4h", "1d", "1w"]


@router.get("/{interval}")
async def get_market_data(interval: Interval):
    """Get market data for a specific interval with chart-ready data."""
    try:
        data = await market_service.get_market_data(interval)
        # Add recent candles for charting if available
        df = market_service.curation.get_latest_curated(interval)
        if df is not None and not df.empty:
            recent = df.tail(50).copy()  # Last 50 candles for chart
            data["data"] = [
                {
                    "open_time": row["open_time"].isoformat() if hasattr(row["open_time"], "isoformat") else str(row["open_time"]),
                    "close": float(row["close"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "volume": float(row["volume"]),
                }
                for _, row in recent.iterrows()
            ]
        else:
            # Ensure data key exists even if no candles
            if "data" not in data:
                data["data"] = []
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

