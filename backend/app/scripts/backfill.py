"""CLI script for backfilling historical data."""
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.data.ingestion import DataIngestion
from app.core.logging import logger


async def backfill_interval(interval: str, days: int = 30):
    """Backfill data for a specific interval."""
    di = DataIngestion()
    end = datetime.utcnow()
    start = end - timedelta(days=days)
    
    logger.info(f"Backfilling {interval} from {start.date()} to {end.date()}")
    result = await di.ingest_timeframe(interval, start, end)
    
    if result.get("status") == "success":
        logger.info(f"✓ Successfully backfilled {interval}: {result.get('rows', 0)} rows")
        return True
    else:
        logger.error(f"✗ Failed to backfill {interval}: {result.get('error', 'Unknown error')}")
        return False


async def backfill_all(days: int = 30):
    """Backfill all timeframes."""
    intervals = ["15m", "30m", "1h", "4h", "1d", "1w"]
    results = []
    
    for interval in intervals:
        success = await backfill_interval(interval, days)
        results.append((interval, success))
        # Small delay between intervals
        await asyncio.sleep(1)
    
    failed = [i for i, s in results if not s]
    if failed:
        logger.warning(f"Failed intervals: {', '.join(failed)}")
        return 1
    else:
        logger.info("✓ All intervals backfilled successfully")
        return 0


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Backfill historical market data")
    parser.add_argument(
        "--interval",
        choices=["15m", "30m", "1h", "4h", "1d", "1w", "all"],
        default="all",
        help="Timeframe to backfill (default: all)"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to backfill (default: 30)"
    )
    
    args = parser.parse_args()
    
    if args.interval == "all":
        exit_code = asyncio.run(backfill_all(args.days))
    else:
        success = asyncio.run(backfill_interval(args.interval, args.days))
        exit_code = 0 if success else 1
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

