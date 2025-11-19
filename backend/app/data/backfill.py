"""Command-line backfill utility for historical ingestion."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from typing import Sequence

from app.core.logging import logger
from app.data.exchanges import (
    BinanceFuturesUSDTDataSource,
    BitstampDataSource,
    CoinbaseDataSource,
)
from app.data.monitoring import DataAuditTrail, IngestionWindow
from app.data.multi_ingestion import MultiVenueIngestion
from app.data.scheduler import BackfillScheduler


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run historical backfill across venues.")
    parser.add_argument("--symbol", required=True, help="Market symbol, e.g., BTCUSDT")
    parser.add_argument("--interval", required=True, help="Interval alias, e.g., 1h")
    parser.add_argument("--start", required=True, help="Start timestamp (ISO format)")
    parser.add_argument("--end", required=True, help="End timestamp (ISO format)")
    parser.add_argument(
        "--venues",
        default="binance,coinbase,bitstamp",
        help="Comma separated venues: binance,coinbase,bitstamp",
    )
    return parser.parse_args()


def _build_sources(requested: Sequence[str]):
    mapping = {
        "binance": BinanceFuturesUSDTDataSource(),
        "coinbase": CoinbaseDataSource(),
        "bitstamp": BitstampDataSource(),
    }
    sources = []
    for key in requested:
        source = mapping.get(key.strip())
        if source:
            sources.append(source)
    if not sources:
        raise ValueError("No valid venues specified")
    return sources


async def _run() -> None:
    args = _parse_args()
    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)
    if start >= end:
        raise ValueError("Start must be before end")
    venues = [v.strip() for v in args.venues.split(",") if v.strip()]
    sources = _build_sources(venues)

    ingestion = MultiVenueIngestion(sources=sources)
    monitor = DataAuditTrail(venues=[src.venue for src in sources])
    scheduler = BackfillScheduler(ingestion=ingestion, monitor=monitor)

    windows = _enumerate_windows(start, end, args.interval)
    logger.info(
        "Starting backfill",
        extra={"symbol": args.symbol, "interval": args.interval, "windows": len(windows), "venues": venues},
    )
    await scheduler.run_backfill(args.symbol, args.interval, windows)
    logger.info("Backfill complete", extra={"symbol": args.symbol, "interval": args.interval})


def _enumerate_windows(start: datetime, end: datetime, interval: str) -> list[IngestionWindow]:
    from app.data.monitoring import DataAuditTrail

    span = DataAuditTrail._interval_to_timedelta(interval)
    windows: list[IngestionWindow] = []
    cursor = start
    while cursor < end:
        next_end = min(cursor + span, end)
        windows.append(IngestionWindow(start=cursor, end=next_end))
        cursor = next_end
    return windows


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()






