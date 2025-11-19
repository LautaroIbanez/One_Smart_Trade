"""Async scheduler utilities for ingestion and backfill jobs."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from app.core.logging import logger
from app.data.monitoring import DataAuditTrail, IngestionWindow
from app.data.multi_ingestion import MultiVenueIngestion


@dataclass(slots=True)
class BackfillScheduler:
    """Coordinate periodic ingestion jobs with retry and auditing."""

    ingestion: MultiVenueIngestion
    monitor: DataAuditTrail
    max_retries: int = 3
    retry_backoff_seconds: float = 5.0

    async def run_interval_job(self, symbol: str, interval: str) -> dict:
        window = self.monitor.next_window(symbol, interval)
        logger.info(
            "Starting ingestion window",
            extra={
                "symbol": symbol,
                "interval": interval,
                "start": window.start.isoformat(),
                "end": window.end.isoformat(),
            },
        )
        result = await self._run_with_retries(symbol, interval, window)
        self.monitor.record(symbol, interval, window.start, window.end, result)
        return result

    async def run_backfill(
        self,
        symbol: str,
        interval: str,
        windows: Iterable[IngestionWindow],
    ) -> list[dict]:
        results = []
        for window in windows:
            logger.info(
                "Backfill window",
                extra={
                    "symbol": symbol,
                    "interval": interval,
                    "start": window.start.isoformat(),
                    "end": window.end.isoformat(),
                },
            )
            result = await self._run_with_retries(symbol, interval, window)
            self.monitor.record(symbol, interval, window.start, window.end, result)
            results.append(result)
        return results

    async def _run_with_retries(self, symbol: str, interval: str, window: IngestionWindow) -> dict:
        attempt = 0
        last_error: Exception | None = None
        while attempt < self.max_retries:
            try:
                return await self.ingestion.ingest_interval(
                    symbol,
                    interval,
                    start=window.start,
                    end=window.end,
                )
            except Exception as exc:
                attempt += 1
                last_error = exc
                logger.warning(
                    "Ingestion attempt failed",
                    extra={
                        "attempt": attempt,
                        "max_retries": self.max_retries,
                        "symbol": symbol,
                        "interval": interval,
                        "error": str(exc),
                    },
                )
                await asyncio.sleep(self.retry_backoff_seconds * attempt)
        if last_error:
            raise last_error
        raise RuntimeError("Ingestion failed without raising exception")






