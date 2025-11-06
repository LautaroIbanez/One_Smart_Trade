"""Prometheus metrics integration and request latency middleware."""
from __future__ import annotations

import time
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi import APIRouter


REQUEST_COUNT = Counter(
    'ost_http_requests_total', 'Total HTTP requests', ['method', 'path', 'status']
)
REQUEST_LATENCY = Histogram(
    'ost_http_request_latency_seconds', 'Request latency in seconds', ['method', 'path']
)


class RequestMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        method = request.method
        path = request.url.path
        start = time.time()
        try:
            response = await call_next(request)
            return response
        finally:
            latency = time.time() - start
            status = getattr(request.state, 'status_code', 200)
            REQUEST_LATENCY.labels(method=method, path=path).observe(latency)
            REQUEST_COUNT.labels(method=method, path=path, status=str(status)).inc()


metrics_router = APIRouter()


@metrics_router.get('/metrics')
async def metrics() -> Response:
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


