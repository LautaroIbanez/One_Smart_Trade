"""CLI script for backfilling historical data."""
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.data.ingestion import DataIngestion
from app.observability.metrics import record_ingestion
from app.core.logging import logger
import time


async def backfill_interval(interval: str, days: int = 30):
    """Backfill data for a specific interval with metrics recording."""
    di = DataIngestion()
    end = datetime.utcnow()
    start = end - timedelta(days=days)
    
    logger.info(f"Backfilling {interval} from {start.date()} to {end.date()}")
    start_time = time.time()
    
    try:
        result = await di.ingest_timeframe(interval, start, end)
        duration = time.time() - start_time
        
        if result.get("status") == "success":
            logger.info(f"✓ Successfully backfilled {interval}: {result.get('rows', 0)} rows")
            # Record successful ingestion with correct timeframe
            record_ingestion(interval, duration, True)
            return True
        else:
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"✗ Failed to backfill {interval}: {error_msg}")
            # Record failed ingestion with correct timeframe
            record_ingestion(interval, duration, False, error_msg)
            return False
    except Exception as e:
        duration = time.time() - start_time
        error_msg = str(e)
        logger.error(f"✗ Exception during backfill {interval}: {error_msg}", exc_info=True)
        record_ingestion(interval, duration, False, type(e).__name__)
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

