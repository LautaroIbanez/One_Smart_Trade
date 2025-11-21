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

INGESTION_SUCCESS = Counter("ingestion_success_total", "Ingestiones exitosas")
INGESTION_FAILURE = Counter(
    "ingestion_failure_total", "Ingestiones fallidas", ["error"]
)
INGESTION_LATENCY = Histogram("ingestion_latency_seconds", "Latencia de ingestión")

SIGNAL_SUCCESS = Counter("signal_generation_success_total", "Señales generadas con éxito")
SIGNAL_FAILURE = Counter(
    "signal_generation_failure_total", "Señales fallidas", ["error"]
)
SIGNAL_LATENCY = Histogram(
    "signal_generation_latency_seconds", "Latencia de generación de señal"
)
LAST_SIGNAL_TS = Gauge(
    "signal_generation_last_timestamp", "Última señal exitosa (epoch)"
)
DATA_GAPS = Counter(
    "data_gaps_total", "Gaps detectados en datasets", ["timeframe"]
)

# Binance client metrics
BINANCE_REQUEST_LATENCY = Histogram(
    "binance_request_latency_seconds",
    "Latency of Binance API requests",
    ["symbol", "interval"],
)

# API endpoint response time metrics
ENDPOINT_RESPONSE_TIME = Histogram(
    "endpoint_response_time_seconds",
    "Response time for API endpoints",
    ["endpoint", "status"],
)

# Cache metrics
CACHE_HITS = Counter("cache_hits_total", "Cache hits", ["cache_key"])
CACHE_MISSES = Counter("cache_misses_total", "Cache misses", ["cache_key"])


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


def record_ingestion(interval: str, latency_s: float, success: bool, error: str | None = None) -> None:
    if success:
        INGESTION_SUCCESS.inc()
    else:
        INGESTION_FAILURE.labels(error or "unknown").inc()
    INGESTION_LATENCY.observe(latency_s)


def record_signal_generation(latency_s: float, success: bool, error: str | None = None) -> None:
    if success:
        SIGNAL_SUCCESS.inc()
        LAST_SIGNAL_TS.set_to_current_time()
    else:
        SIGNAL_FAILURE.labels(error or "unknown").inc()
    SIGNAL_LATENCY.observe(latency_s)


def record_data_gap(timeframe: str) -> None:
    DATA_GAPS.labels(timeframe=timeframe).inc()


