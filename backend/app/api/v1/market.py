"""Market data endpoints."""
from typing import Literal
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.services.market_service import MarketService
from app.utils.cache import get_cached, set_cached
from app.observability.metrics import ENDPOINT_RESPONSE_TIME
from app.core import pipeline_state
from app.core.logging import logger

router = APIRouter()
market_service = MarketService()

Interval = Literal["15m", "30m", "1h", "4h", "1d", "1w"]


@router.get("/{interval}")
async def get_market_data(
    interval: Interval,
    window: int = 200,
):
    """
    Get market data for a specific interval with chart-ready data.
    
    Args:
        interval: Timeframe (15m, 30m, 1h, 4h, 1d, 1w)
        window: Number of recent candles to return (default: 200, max: 1000)
    
    Results are cached for 60 seconds to reduce load on data curation layer.
    Cache key includes generated_at timestamp to invalidate on new pipeline runs.
    """
    start_time = time.time()
    
    # Limit window size
    window = min(max(window, 1), 1000)

    # If the startup pipeline is warming up, return a fast 202 so the frontend can poll
    # instead of waiting for a 25s timeout while the pipeline holds resources.
    if pipeline_state.is_running():
        return JSONResponse(
            status_code=202,
            content={
                "status": "processing",
                "reason": "Startup pipeline en ejecución. Vuelve a intentar en unos momentos.",
                "pipeline": pipeline_state.get_status().to_dict(),
            },
        )
    
    # Get metadata to include in cache key (for invalidation on new pipeline runs)
    try:
        metadata = market_service.curation.get_curated_metadata(interval)
        generated_at = metadata.get("generated_at") if metadata else None
        latest_open_time = metadata.get("latest_open_time") if metadata else None
        # Use latest_open_time or generated_at as cache key component
        cache_version = latest_open_time or generated_at or "unknown"
    except Exception:
        cache_version = "unknown"
    
    # Check cache with version-aware key
    cached_result = get_cached("market_data", interval=interval, window=window, cache_version=cache_version, ttl_seconds=60.0)
    if cached_result:
        duration = time.time() - start_time
        ENDPOINT_RESPONSE_TIME.labels(endpoint=f"/market/{interval}", status="cached").observe(duration)
        # Mark as served from cache
        if isinstance(cached_result, dict):
            if "metadata" not in cached_result:
                cached_result["metadata"] = {}
            cached_result["metadata"]["served_from_cache"] = True
        # Deduplicate cache-served logs: sample at 10% or elevate to debug
        import random
        if random.random() < 0.1:  # Sample 10% of cache hits
            logger.info(
                f"Returning cached market data for {interval} (sampled)",
                extra={"interval": interval, "window": window, "log_sampled": True},
            )
        else:
            logger.debug(f"Returning cached market data for {interval}")
        return cached_result
    
    try:
        data = await market_service.get_market_data(interval, window=window)
        # Add recent candles for charting if available (use configurable window)
        df = market_service.curation.get_latest_curated(interval)
        if df is not None and not df.empty:
            recent = df.tail(window).copy()  # Use configurable window
            # FE-DATA-01: Ensure data structure matches frontend MarketPoint interface expectations
            # Frontend expects: timestamp, open, high, low, close, volume
            data["data"] = [
                {
                    "open_time": row["open_time"].isoformat() if hasattr(row["open_time"], "isoformat") else str(row["open_time"]),
                    "timestamp": row["open_time"].isoformat() if hasattr(row["open_time"], "isoformat") else str(row["open_time"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                }
                for _, row in recent.iterrows()
            ]
        else:
            # Ensure data key exists even if no candles
            if "data" not in data:
                data["data"] = []
        
        # Ensure metadata exists and mark as not from cache
        if "metadata" not in data:
            data["metadata"] = {}
        data["metadata"]["served_from_cache"] = False
        
        # Include as_of timestamp matching parquet metadata
        if metadata:
            if "latest_open_time" in metadata:
                data["metadata"]["as_of"] = metadata["latest_open_time"]
            elif "generated_at" in metadata:
                data["metadata"]["as_of"] = metadata["generated_at"]
        
        # Cache result with version-aware key
        set_cached("market_data", data, interval=interval, window=window, cache_version=cache_version, ttl_seconds=60.0)
        
        duration = time.time() - start_time
        status_label = data.get("status", "success")
        ENDPOINT_RESPONSE_TIME.labels(endpoint=f"/market/{interval}", status=status_label).observe(duration)
        
        # Return 503 if data is stale
        if data.get("status") == "data_stale":
            return JSONResponse(
                status_code=503,
                content=data,
            )
        
        return data
    except Exception as e:
        duration = time.time() - start_time
        ENDPOINT_RESPONSE_TIME.labels(endpoint=f"/market/{interval}", status="error").observe(duration)
        raise HTTPException(status_code=500, detail=str(e))

