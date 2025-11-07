"""CLI script for backfilling historical data."""
from __future__ import annotations

import asyncio
from datetime import datetime

import click

from app.core.logging import logger
from app.data.curation import DataCuration
from app.data.ingestion import INTERVALS, DataIngestion


async def _backfill_async(interval: str, since: datetime | None) -> None:
    """Backfill historical data for a specific interval."""
    ingestion = DataIngestion()
    logger.info(f"Starting backfill for {interval}" + (f" since {since.date()}" if since else ""))

    try:
        await ingestion.ingest_timeframe(interval, start=since)
        logger.info(f"✓ Ingested data for {interval}")

        curation = DataCuration()
        curation.curate_interval(interval)
        logger.info(f"✓ Curated data for {interval}")
    except Exception as e:
        logger.error(f"✗ Failed to backfill {interval}: {e}", exc_info=True)
        raise click.ClickException(str(e))


@click.command()
@click.option("--interval", required=True, type=click.Choice(INTERVALS))
@click.option("--since", type=click.DateTime(formats=["%Y-%m-%d"]))
def backfill(interval: str, since: datetime | None) -> None:
    """Backfill historical data for a specific interval."""
    asyncio.run(_backfill_async(interval, since))


if __name__ == "__main__":
    backfill()

