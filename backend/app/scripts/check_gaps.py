"""CLI script for checking data gaps."""
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.data.curation import DataCuration
from app.data.ingestion import DataIngestion
from app.core.logging import logger


def check_gaps(interval: str, days: int = 30):
    """Check for gaps in data."""
    dc = DataCuration()
    di = DataIngestion()
    
    end = datetime.utcnow()
    start = end - timedelta(days=days)
    
    logger.info(f"Checking gaps for {interval} from {start.date()} to {end.date()}")
    
    # Get curated data
    df = dc.get_historical_curated(interval, start_date=start, end_date=end)
    
    if df is None or df.empty:
        logger.warning(f"No data available for {interval}")
        return []
    
    # Check gaps using ingestion method
    gaps = di.check_gaps(interval, start, end)
    
    if gaps:
        logger.warning(f"Found {len(gaps)} gap(s) in {interval}:")
        for gap in gaps:
            logger.warning(f"  - {gap}")
    else:
        logger.info(f"✓ No gaps found in {interval}")
    
    return gaps


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Check for data gaps")
    parser.add_argument(
        "--interval",
        choices=["15m", "30m", "1h", "4h", "1d", "1w", "all"],
        default="all",
        help="Timeframe to check (default: all)"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to check (default: 30)"
    )
    
    args = parser.parse_args()
    
    intervals = ["15m", "30m", "1h", "4h", "1d", "1w"] if args.interval == "all" else [args.interval]
    
    all_gaps = {}
    for interval in intervals:
        gaps = check_gaps(interval, args.days)
        if gaps:
            all_gaps[interval] = gaps
    
    if all_gaps:
        logger.warning(f"Gaps found in {len(all_gaps)} interval(s)")
        sys.exit(1)
    else:
        logger.info("✓ No gaps found in any interval")
        sys.exit(0)


if __name__ == "__main__":
    main()

