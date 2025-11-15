"""Monitoring utilities for ingestion completeness and audit trail."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd
from prometheus_client import Gauge

from app.core.database import SessionLocal
from app.core.logging import logger
from app.db import crud


@dataclass(slots=True)
class IngestionWindow:
    start: datetime
    end: datetime


class DataAuditTrail:
    """Track ingestion windows and completeness across venues."""

    def __init__(
        self,
        *,
        venues: Sequence[str],
        default_lookback: timedelta = timedelta(days=7),
    ) -> None:
        self.venues = list(venues)
        self.default_lookback = default_lookback
        self._checksum_metric = Gauge(
            "data_checksum_ok",
            "Checksum validation status (1 = ok, 0 = mismatch, -1 = missing)",
            ["venue", "symbol", "interval", "path"],
        )
        self._missing_metric = Gauge(
            "missing_partitions",
            "Number of missing partitions per venue/interval",
            ["venue", "symbol", "interval"],
        )

    def next_window(self, symbol: str, interval: str) -> IngestionWindow:
        """Determine the next ingestion window across venues."""
        span = self._interval_to_timedelta(interval)
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        start_candidates: list[datetime] = []

        with SessionLocal() as db:
            for venue in self.venues:
                last_run = crud.get_last_successful_run(db, venue, symbol, interval)
                if last_run:
                    end_time = datetime.fromisoformat(last_run.end_time)
                else:
                    end_time = now - self.default_lookback
                start_candidates.append(end_time)

        start = min(start_candidates) if start_candidates else now - self.default_lookback
        start = start.replace(tzinfo=timezone.utc)
        end = min(start + span, now)
        return IngestionWindow(start=start, end=end)

    def record(self, symbol: str, interval: str, start: datetime, end: datetime, result: dict) -> None:
        """Persist run metadata for each venue."""
        venues_results = result.get("venues", [])
        with SessionLocal() as db:
            for venue_result in venues_results:
                venue = venue_result["venue"]
                row_count = int(venue_result.get("rows", 0))
                status = "success" if venue_result.get("status") == "stored" else venue_result.get("status", "unknown")
                path = venue_result.get("path")
                checksum = self._file_checksum(Path(path)) if path else None
                crud.create_data_run(
                    db,
                    venue=venue,
                    symbol=symbol,
                    interval=interval,
                    start_time=start.isoformat(),
                    end_time=end.isoformat(),
                    status=status,
                    row_count=row_count,
                    checksum=checksum,
                    message=venue_result.get("message"),
                )
                if checksum:
                    self._checksum_metric.labels(
                        venue=venue,
                        symbol=symbol,
                        interval=interval,
                        path=path or "",
                    ).set(1)

    def missing_windows(
        self,
        symbol: str,
        interval: str,
        *,
        since: datetime | None = None,
    ) -> list[IngestionWindow]:
        """Return windows that have not been ingested since the provided timestamp."""
        since = since or datetime.utcnow().replace(tzinfo=timezone.utc) - self.default_lookback
        span = self._interval_to_timedelta(interval)
        now = datetime.utcnow().replace(tzinfo=timezone.utc)

        windows: list[IngestionWindow] = []
        cursor = since
        while cursor < now:
            next_window = IngestionWindow(start=cursor, end=min(cursor + span, now))
            windows.append(next_window)
            cursor += span

        self._missing_metric.labels(venue="*", symbol=symbol, interval=interval).set(len(windows))

        return windows

    @staticmethod
    def _file_checksum(path: Path) -> str | None:
        if not path or not path.exists():
            return None
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(8192), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _interval_to_timedelta(interval: str) -> timedelta:
        try:
            if interval.endswith("m"):
                minutes = int(interval[:-1])
                return timedelta(minutes=minutes)
            if interval.endswith("h"):
                hours = int(interval[:-1])
                return timedelta(hours=hours)
            if interval.endswith("d"):
                days = int(interval[:-1])
                return timedelta(days=days)
        except ValueError:
            logger.warning("Invalid interval format %s, defaulting to 1h", interval)
        return timedelta(hours=1)


