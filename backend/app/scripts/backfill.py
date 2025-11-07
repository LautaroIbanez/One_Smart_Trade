from __future__ import annotations

import asyncio
from datetime import datetime

import click

from app.data.curation import DataCuration
from app.data.ingestion import DataIngestion, INTERVALS


@click.command()
@click.option("--interval", type=click.Choice(INTERVALS), required=True)
@click.option("--since", type=click.DateTime(formats=["%Y-%m-%d"]), default=None)
@click.option("--until", type=click.DateTime(formats=["%Y-%m-%d"]), default=None)
def main(interval: str, since: datetime | None, until: datetime | None) -> None:
    ingestion = DataIngestion()
    curation = DataCuration()

    async def _run() -> None:
        await ingestion.ingest_timeframe(interval, start=since, end=until)
        curation.curate_interval(interval)

    asyncio.run(_run())


if __name__ == "__main__":
    main()

