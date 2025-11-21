"""CLI script for checking data gaps."""
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.logging import logger  # noqa: E402
from app.data.curation import DataCuration  # noqa: E402
from app.data.ingestion import DataIngestion  # noqa: E402
from app.observability.metrics import record_data_gap  # noqa: E402


def check_gaps(interval: str, days: int = 30):
    """Check for gaps in data."""
    dc = DataCuration()
    di = DataIngestion()

    end = datetime.utcnow()
    start = end - timedelta(days=days)

    logger.info(f"Checking gaps for {interval} from {start.date()} to {end.date()}")

    # Get curated data (new API supports start_date/end_date)
    try:
        df = dc.get_historical_curated(interval, start_date=start, end_date=end)
    except Exception as e:
        logger.warning(f"Error loading curated data for {interval}: {e}")
        df = None

    if df is None or df.empty:
        logger.warning(f"No data available for {interval}")
        return []

    # Check gaps using ingestion method
    gaps = di.check_gaps(interval, start, end)

    if gaps:
        logger.warning(f"Found {len(gaps)} gap(s) in {interval}:")
        for gap in gaps:
            logger.warning(f"  - {gap}")
            # Record gap in metrics with error handling - don't let metric failures interrupt gap checking
            try:
                record_data_gap(interval)
            except (ValueError, Exception) as metric_error:
                logger.warning(
                    f"Failed to record data gap metric for {interval}: {metric_error}",
                    extra={"interval": interval, "error_type": type(metric_error).__name__, "error": str(metric_error)},
                    exc_info=False,
                )
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

