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
    # BE-CACHE-01: Always read fresh metadata to ensure cache key reflects latest data
    try:
        metadata = market_service.curation.get_curated_metadata(interval)
        generated_at = metadata.get("generated_at") if metadata else None
        latest_open_time = metadata.get("latest_open_time") if metadata else None
        # Use latest_open_time or generated_at as cache key component
        cache_version = latest_open_time or generated_at or "unknown"
        # Log metadata freshness for observability
        if latest_open_time:
            logger.debug(
                f"Cache key built from metadata for {interval}",
                extra={
                    "interval": interval,
                    "latest_open_time": latest_open_time,
                    "generated_at": generated_at,
                    "cache_version": cache_version,
                },
            )
    except Exception as exc:
        logger.warning(
            f"Failed to read metadata for cache key for {interval}: {exc}",
            extra={"interval": interval, "error": str(exc)},
        )
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
            # FE-CHART-01: Ensure DataFrame is sorted by open_time before taking tail
            # This ensures we get the most recent candles, not just the last rows by index
            if "open_time" in df.columns:
                # Sort by open_time to ensure chronological order (oldest to newest)
                df_sorted = df.sort_values("open_time").copy()
                # Take the last window candles (most recent)
                recent = df_sorted.tail(window).copy()
                
                # FE-CHART-01: Validate that returned data includes the latest candle from metadata
                if metadata and "latest_open_time" in metadata:
                    latest_open_time_str = metadata["latest_open_time"]
                    try:
                        from datetime import datetime, timezone
                        if isinstance(latest_open_time_str, str):
                            latest_open_time_dt = datetime.fromisoformat(latest_open_time_str.replace("Z", "+00:00"))
                        else:
                            latest_open_time_dt = latest_open_time_str
                        if latest_open_time_dt.tzinfo is None:
                            latest_open_time_dt = latest_open_time_dt.replace(tzinfo=timezone.utc)
                        
                        # Check if the latest candle from metadata is in the returned data
                        recent_open_times = recent["open_time"].tolist()
                        if recent_open_times:
                            recent_latest = max(recent_open_times)
                            # Compare timestamps (allow 1 minute tolerance for rounding)
                            time_diff = abs((recent_latest - latest_open_time_dt).total_seconds())
                            if time_diff > 60:  # More than 1 minute difference
                                logger.warning(
                                    f"FE-CHART-01: Returned data does not include latest candle from metadata",
                                    extra={
                                        "interval": interval,
                                        "window": window,
                                        "metadata_latest": latest_open_time_str,
                                        "returned_latest": recent_latest.isoformat() if hasattr(recent_latest, "isoformat") else str(recent_latest),
                                        "time_diff_seconds": time_diff,
                                        "total_rows_in_df": len(df),
                                        "rows_returned": len(recent),
                                        "actionable_error": True,
                                    },
                                )
                    except Exception as validation_exc:
                        logger.warning(
                            f"FE-CHART-01: Could not validate latest candle timestamp: {validation_exc}",
                            extra={"interval": interval, "error": str(validation_exc)},
                        )
            else:
                # Fallback: use tail if open_time column is missing
                recent = df.tail(window).copy()
                logger.warning(
                    f"FE-CHART-01: DataFrame missing open_time column, using tail() without sorting",
                    extra={"interval": interval, "columns": list(df.columns)},
                )
            
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
        
        # BE-CACHE-01: Log age_minutes for observability and cache freshness tracking
        age_minutes = data.get("metadata", {}).get("age_minutes")
        if age_minutes is not None:
            logger.info(
                f"Market data served for {interval}",
                extra={
                    "interval": interval,
                    "age_minutes": age_minutes,
                    "status": status_label,
                    "window": window,
                    "cache_version": cache_version,
                    "latest_open_time": metadata.get("latest_open_time") if metadata else None,
                },
            )
            # BE-CACHE-01: Only log warning if data is approaching stale threshold
            # Use the same threshold logic as MarketService for consistency
            threshold_minutes = market_service.curation._get_freshness_threshold_minutes(interval)
            # Only warn if age is > 80% of threshold AND status is not already stale
            # This prevents false warnings immediately after successful ingestion
            if age_minutes > threshold_minutes * 0.8 and status_label != "data_stale":
                logger.warning(
                    f"Market data approaching stale threshold for {interval}",
                    extra={
                        "interval": interval,
                        "age_minutes": age_minutes,
                        "threshold_minutes": threshold_minutes,
                        "status": status_label,
                        "latest_open_time": metadata.get("latest_open_time") if metadata else None,
                    },
                )
        
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

