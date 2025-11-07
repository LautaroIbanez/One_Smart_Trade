from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Sequence

import httpx

BASE_URL = "https://api.binance.com"
KLINES_PATH = "/api/v3/klines"
REQUESTS_PER_MINUTE = 1100
WINDOW_SECONDS = 60.0


class _RateLimiter:
    """Simple token bucket to respect Binance rate limits."""

    def __init__(self, max_requests: int, window: float) -> None:
        self._max = max_requests
        self._window = window
        loop = asyncio.get_event_loop()
        self._last_refill = loop.time()
        self._tokens = max_requests
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_refill
            if elapsed >= self._window:
                self._tokens = self._max
                self._last_refill = now
            while self._tokens <= 0:
                await asyncio.sleep(0.05)
                now = asyncio.get_event_loop().time()
                elapsed = now - self._last_refill
                if elapsed >= self._window:
                    self._tokens = self._max
                    self._last_refill = now
            self._tokens -= 1


_rate_limiter = _RateLimiter(REQUESTS_PER_MINUTE, WINDOW_SECONDS)


class BinanceClient:
    """Async client for Binance public klines endpoint."""

    def __init__(self, base_url: str = BASE_URL) -> None:
        self._base_url = base_url

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> tuple[Sequence[list[Any]], dict[str, Any]]:
        params: dict[str, Any] = {"symbol": symbol, "interval": interval, "limit": limit}
        if start is not None:
            params["startTime"] = int(start.timestamp() * 1000)
        if end is not None:
            params["endTime"] = int(end.timestamp() * 1000)

        await _rate_limiter.acquire()
        async with httpx.AsyncClient(base_url=self._base_url, timeout=30.0) as client:
            response = await client.get(KLINES_PATH, params=params)
            response.raise_for_status()
            data = response.json()

        latency_ms = 0.0
        try:
            latency_ms = float(response.elapsed.total_seconds() * 1000)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 - best effort metadata
            try:
                latency_value = float(getattr(response, "elapsed", 0.0))
                latency_ms = latency_value * 1000
            except Exception:  # pragma: no cover - ignore metadata errors
                latency_ms = 0.0

        meta = {
            "symbol": symbol,
            "interval": interval,
            "requested_limit": limit,
            "fetched_at": datetime.utcnow().isoformat(),
            "latency_ms": latency_ms,
        }
        return data, meta