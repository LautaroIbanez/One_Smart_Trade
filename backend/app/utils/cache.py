"""
Simple in-memory cache with TTL for API responses.

This provides a lightweight caching solution for expensive operations
without requiring external dependencies like Redis.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Callable, TypeVar

from app.core.logging import logger
from app.observability.metrics import CACHE_HITS, CACHE_MISSES

T = TypeVar("T")

# Global cache storage
_cache: dict[str, tuple[Any, float]] = {}


def _make_cache_key(prefix: str, *args: Any, **kwargs: Any) -> str:
    """Generate a cache key from prefix, args, and kwargs."""
    key_data = {
        "prefix": prefix,
        "args": args,
        "kwargs": sorted(kwargs.items()) if kwargs else [],
    }
    key_str = json.dumps(key_data, sort_keys=True, default=str)
    return f"{prefix}:{hashlib.sha256(key_str.encode()).hexdigest()[:16]}"


def get_cached(prefix: str, ttl_seconds: float, *args: Any, **kwargs: Any) -> Any | None:
    """
    Get cached value if it exists and hasn't expired.
    
    Args:
        prefix: Cache key prefix
        ttl_seconds: Time-to-live in seconds
        *args, **kwargs: Arguments used to generate cache key
    
    Returns:
        Cached value or None if not found/expired
    """
    cache_key = _make_cache_key(prefix, *args, **kwargs)
    if cache_key in _cache:
        value, expiry = _cache[cache_key]
        if time.time() < expiry:
            logger.debug(f"Cache hit: {prefix}")
            CACHE_HITS.labels(cache_key=prefix).inc()
            return value
        else:
            # Expired, remove it
            del _cache[cache_key]
            logger.debug(f"Cache expired: {prefix}")
    CACHE_MISSES.labels(cache_key=prefix).inc()
    return None


def set_cached(prefix: str, value: Any, ttl_seconds: float, *args: Any, **kwargs: Any) -> None:
    """
    Set a cached value with TTL.
    
    Args:
        prefix: Cache key prefix
        value: Value to cache
        ttl_seconds: Time-to-live in seconds
        *args, **kwargs: Arguments used to generate cache key
    """
    cache_key = _make_cache_key(prefix, *args, **kwargs)
    expiry = time.time() + ttl_seconds
    _cache[cache_key] = (value, expiry)
    logger.debug(f"Cache set: {prefix} (TTL: {ttl_seconds}s)")


def clear_cache(prefix: str | None = None) -> int:
    """
    Clear cache entries.
    
    Args:
        prefix: If provided, only clear entries with this prefix. Otherwise clear all.
    
    Returns:
        Number of entries cleared
    """
    if prefix is None:
        count = len(_cache)
        _cache.clear()
        logger.info(f"Cache cleared: {count} entries")
        return count
    
    # Clear entries with matching prefix
    keys_to_remove = [k for k in _cache.keys() if k.startswith(f"{prefix}:")]
    for key in keys_to_remove:
        del _cache[key]
    logger.info(f"Cache cleared: {len(keys_to_remove)} entries with prefix '{prefix}'")
    return len(keys_to_remove)


def cached(prefix: str, ttl_seconds: float = 300.0):
    """
    Decorator to cache function results.
    
    Args:
        prefix: Cache key prefix
        ttl_seconds: Time-to-live in seconds (default: 5 minutes)
    
    Example:
        @cached("market_data", ttl_seconds=60.0)
        async def get_market_data(interval: str):
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        async def async_wrapper(*args: Any, **kwargs: Any) -> T:
            # Check cache
            cached_value = get_cached(prefix, ttl_seconds, *args, **kwargs)
            if cached_value is not None:
                return cached_value
            
            # Call function and cache result
            result = await func(*args, **kwargs)
            set_cached(prefix, result, ttl_seconds, *args, **kwargs)
            return result
        
        def sync_wrapper(*args: Any, **kwargs: Any) -> T:
            # Check cache
            cached_value = get_cached(prefix, ttl_seconds, *args, **kwargs)
            if cached_value is not None:
                return cached_value
            
            # Call function and cache result
            result = func(*args, **kwargs)
            set_cached(prefix, result, ttl_seconds, *args, **kwargs)
            return result
        
        # Return appropriate wrapper based on whether function is async
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        else:
            return sync_wrapper  # type: ignore
    
    return decorator

