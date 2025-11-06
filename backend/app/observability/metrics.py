"""Prometheus metrics integration and request latency middleware."""
from __future__ import annotations

import time
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import APIRouter


REQUEST_COUNT = Counter(
    'ost_http_requests_total', 'Total HTTP requests', ['method', 'path', 'status']
)
REQUEST_LATENCY = Histogram(
    'ost_http_request_latency_seconds', 'Request latency in seconds', ['method', 'path']
)

# Scheduler metrics
INGESTION_DURATION = Histogram(
    'ost_ingestion_duration_seconds', 'Data ingestion duration', ['timeframe']
)
INGESTION_FAILURES = Counter(
    'ost_ingestion_failures_total', 'Total ingestion failures', ['timeframe', 'reason']
)
SIGNAL_GENERATION_DURATION = Histogram(
    'ost_signal_generation_duration_seconds', 'Signal generation duration'
)
SIGNAL_GENERATION_FAILURES = Counter(
    'ost_signal_generation_failures_total', 'Total signal generation failures', ['reason']
)

# Data quality metrics
LAST_INGESTION_TIME = Gauge(
    'ost_last_ingestion_timestamp_seconds', 'Last successful ingestion timestamp', ['timeframe']
)
LAST_SIGNAL_TIME = Gauge(
    'ost_last_signal_timestamp_seconds', 'Last successful signal generation timestamp'
)
DATA_GAPS = Counter(
    'ost_data_gaps_total', 'Total data gaps detected', ['timeframe']
)


class RequestMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        method = request.method
        path = request.url.path
        start = time.time()
        try:
            response = await call_next(request)
            status_code = response.status_code
            REQUEST_COUNT.labels(method=method, path=path, status=str(status_code)).inc()
            return response
        finally:
            latency = time.time() - start
            REQUEST_LATENCY.labels(method=method, path=path).observe(latency)


metrics_router = APIRouter()


@metrics_router.get('/metrics')
async def metrics() -> Response:
    """Prometheus metrics endpoint."""
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


def record_ingestion(timeframe: str, duration: float, success: bool, reason: str = ""):
    """Record ingestion metrics."""
    if success:
        INGESTION_DURATION.labels(timeframe=timeframe).observe(duration)
        LAST_INGESTION_TIME.labels(timeframe=timeframe).set(time.time())
    else:
        INGESTION_FAILURES.labels(timeframe=timeframe, reason=reason).inc()


def record_signal_generation(duration: float, success: bool, reason: str = ""):
    """Record signal generation metrics."""
    if success:
        SIGNAL_GENERATION_DURATION.observe(duration)
        LAST_SIGNAL_TIME.set(time.time())
    else:
        SIGNAL_GENERATION_FAILURES.labels(reason=reason).inc()


def record_data_gap(timeframe: str):
    """Record data gap detection."""
    DATA_GAPS.labels(timeframe=timeframe).inc()


