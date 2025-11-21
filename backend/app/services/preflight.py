from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import logger
from app.data.curation import DataCuration
from app.data.ingestion import INTERVALS, DataIngestion
from app.db.crud import log_run
from app.observability.metrics import record_data_gap


async def run_preflight(
    *,
    days: int | None = None,
    intervals: tuple[str, ...] | None = None,
    backfill_chunk: int | None = None,
) -> None:
    lookback_days = days or settings.PRESTART_LOOKBACK_DAYS
    selected_intervals = intervals or INTERVALS
    chunk_size = backfill_chunk or settings.PRESTART_BACKFILL_CHUNK

    ingestion = DataIngestion()
    curation = DataCuration()

    now = datetime.utcnow()
    lookback_start = now - timedelta(days=lookback_days)

    logger.info("Starting preflight maintenance (lookback=%s days)", lookback_days)

    db = SessionLocal()
    summary: dict[str, Any] = {"started_at": now.isoformat(), "lookback_days": lookback_days, "intervals": []}

    try:
        for interval in selected_intervals:
            interval_summary: dict[str, Any] = {"interval": interval, "gaps": [], "ingestion": [], "curation": None}
            try:
                gaps = ingestion.check_gaps(interval, lookback_start, now)
            except Exception as exc:
                logger.exception("Preflight gap detection failed for %s", interval)
                interval_summary["gap_error"] = str(exc)
                summary["intervals"].append(interval_summary)
                continue

            interval_summary["gaps"] = gaps

            for gap in gaps:
                if gap.get("status") != "gap":
                    continue
                # Record metric with error handling - don't let metric failures interrupt ingestion
                try:
                    record_data_gap(interval)
                except (ValueError, Exception) as metric_error:
                    # Log warning but continue - metrics are optional observability, not critical path
                    logger.warning(
                        f"Failed to record data gap metric for {interval}: {metric_error}",
                        extra={"interval": interval, "error_type": type(metric_error).__name__, "error": str(metric_error)},
                        exc_info=False,
                    )
                
                gap_start = _parse_dt(gap.get("start"))
                gap_end = _parse_dt(gap.get("end"))
                if gap_start is None or gap_end is None:
                    continue
                ingestion_results = await _backfill_gap(ingestion, interval, gap_start, gap_end, chunk_size)
                interval_summary["ingestion"].extend(ingestion_results)

            try:
                curation_result = curation.curate_interval(interval)
                interval_summary["curation"] = curation_result
            except Exception as exc:
                logger.exception("Preflight curation failed for %s", interval)
                interval_summary["curation_error"] = str(exc)

            summary["intervals"].append(interval_summary)

        log_run(db, "preflight", "success", "Preflight maintenance completed", summary)
        logger.info("Preflight maintenance completed")
    except Exception:
        db.rollback()
        log_run(db, "preflight", "failed", "Preflight maintenance failed", summary)
        logger.exception("Preflight maintenance failed")
    finally:
        db.close()


async def _backfill_gap(
    ingestion: DataIngestion,
    interval: str,
    start: datetime,
    end: datetime,
    chunk_size: int,
) -> list[dict[str, Any]]:
    if start >= end:
        return []

    expected_delta = _chunk_delta(interval, chunk_size)
    responses: list[dict[str, Any]] = []
    cursor = start

    while cursor < end:
        window_end = min(end, cursor + expected_delta)
        try:
            response = await ingestion.ingest_timeframe(interval, start=cursor, end=window_end)
        except Exception as exc:
            responses.append({"status": "error", "interval": interval, "error": str(exc), "start": cursor.isoformat(), "end": window_end.isoformat()})
            logger.exception("Backfill failed for %s between %s and %s", interval, cursor, window_end)
            break

        response = response | {"start": cursor.isoformat(), "end": window_end.isoformat()}
        responses.append(response)

        if response.get("status") in {"empty", "error"}:
            break

        cursor = window_end + _single_delta(interval)

        await asyncio.sleep(settings.PRESTART_BACKFILL_PAUSE_SECONDS)

    return responses


def _chunk_delta(interval: str, chunk_size: int) -> timedelta:
    return _single_delta(interval) * chunk_size


def _single_delta(interval: str) -> timedelta:
    mapping = {
        "15m": timedelta(minutes=15),
        "30m": timedelta(minutes=30),
        "1h": timedelta(hours=1),
        "4h": timedelta(hours=4),
        "1d": timedelta(days=1),
        "1w": timedelta(weeks=1),
    }
    return mapping[interval]


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None

