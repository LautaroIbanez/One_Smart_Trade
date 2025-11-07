"""Prometheus metrics integration and request latency middleware."""
from __future__ import annotations

import time
from collections.abc import Callable

from fastapi import APIRouter, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

REQUEST_COUNT = Counter(
    "ost_http_requests_total", "Total HTTP requests", ["method", "path", "status"]
)
REQUEST_LATENCY = Histogram(
    "ost_http_request_latency_seconds", "Request latency in seconds", ["method", "path"]
)

# Scheduler metrics
INGESTION_SUCCESS = Counter(
    "ingestion_success_total",
    "Conteo de ingestiones completadas",
)
INGESTION_FAILURE = Counter(
    "ingestion_failure_total",
    "Conteo de ingestiones fallidas",
)
INGESTION_LATENCY = Histogram(
    "ingestion_latency_seconds",
    "Latencia de ingestion en segundos",
)
LAST_INGESTION = Gauge(
    "ingestion_last_timestamp",
    "Marca de tiempo de la última ingestión exitosa",
)

# Legacy metrics (kept for backward compatibility)
INGESTION_DURATION = Histogram(
    "ost_ingestion_duration_seconds", "Data ingestion duration", ["timeframe"]
)
INGESTION_FAILURES = Counter(
    "ost_ingestion_failures_total", "Total ingestion failures", ["timeframe", "reason"]
)
SIGNAL_GENERATION_DURATION = Histogram(
    "ost_signal_generation_duration_seconds", "Signal generation duration"
)
SIGNAL_GENERATION_FAILURES = Counter(
    "ost_signal_generation_failures_total", "Total signal generation failures", ["reason"]
)

# Data quality metrics
LAST_INGESTION_TIME = Gauge(
    "ost_last_ingestion_timestamp_seconds", "Last successful ingestion timestamp", ["timeframe"]
)
LAST_SIGNAL_TIME = Gauge(
    "ost_last_signal_timestamp_seconds", "Last successful signal generation timestamp"
)
DATA_GAPS = Counter(
    "ost_data_gaps_total", "Total data gaps detected", ["timeframe"]
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


@metrics_router.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics endpoint."""
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


def record_ingestion(timeframe: str = "", duration: float = 0.0, success: bool = False, reason: str = "", *, latency_s: float = 0.0, interval: str = ""):
    """
    Record ingestion metrics.

    Supports both old signature (timeframe, duration, success, reason) and new signature (success, latency_s, interval).
    """
    import time

    # Use new signature if provided, otherwise use old signature
    if latency_s > 0 or interval:
        latency = latency_s if latency_s > 0 else duration
        if success:
            INGESTION_SUCCESS.inc()
            LAST_INGESTION.set(time.time())
        else:
            INGESTION_FAILURE.inc()
        INGESTION_LATENCY.observe(latency)

    # Legacy metrics (always record for backward compatibility)
    if timeframe:
        if success:
            INGESTION_DURATION.labels(timeframe=timeframe).observe(duration)
            LAST_INGESTION_TIME.labels(timeframe=timeframe).set(time.time())
        else:
            INGESTION_FAILURES.labels(timeframe=timeframe, reason=reason).inc()
    elif interval:
        # Use interval as timeframe for legacy metrics
        if success:
            INGESTION_DURATION.labels(timeframe=interval).observe(latency_s if latency_s > 0 else duration)
            LAST_INGESTION_TIME.labels(timeframe=interval).set(time.time())
        else:
            INGESTION_FAILURES.labels(timeframe=interval, reason=reason).inc()


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


