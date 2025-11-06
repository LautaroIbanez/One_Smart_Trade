"""Very basic in-memory rate limiting middleware per IP."""
from __future__ import annotations

import time
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int = 120):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.buckets: dict[str, list[float]] = {}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        ip = request.client.host if request.client else "anonymous"
        now = time.time()
        window_start = now - 60
        times = self.buckets.get(ip, [])
        times = [t for t in times if t >= window_start]
        if len(times) >= self.requests_per_minute:
            return Response("Too Many Requests", status_code=429)
        times.append(now)
        self.buckets[ip] = times
        return await call_next(request)


