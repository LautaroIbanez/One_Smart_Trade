"""Market data endpoints."""
from typing import Literal
import time

from fastapi import APIRouter, HTTPException

from app.services.market_service import MarketService
from app.utils.cache import get_cached, set_cached
from app.observability.metrics import ENDPOINT_RESPONSE_TIME

router = APIRouter()
market_service = MarketService()

Interval = Literal["15m", "30m", "1h", "4h", "1d", "1w"]


@router.get("/{interval}")
async def get_market_data(interval: Interval):
    """
    Get market data for a specific interval with chart-ready data.
    
    Results are cached for 60 seconds to reduce load on data curation layer.
    """
    start_time = time.time()
    
    # Check cache
    cached_result = get_cached("market_data", ttl_seconds=60.0, interval)
    if cached_result:
        duration = time.time() - start_time
        ENDPOINT_RESPONSE_TIME.labels(endpoint=f"/market/{interval}", status="cached").observe(duration)
        return cached_result
    
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
        
        # Cache result
        set_cached("market_data", data, ttl_seconds=60.0, interval)
        
        duration = time.time() - start_time
        ENDPOINT_RESPONSE_TIME.labels(endpoint=f"/market/{interval}", status="success").observe(duration)
        
        return data
    except Exception as e:
        duration = time.time() - start_time
        ENDPOINT_RESPONSE_TIME.labels(endpoint=f"/market/{interval}", status="error").observe(duration)
        raise HTTPException(status_code=500, detail=str(e))

