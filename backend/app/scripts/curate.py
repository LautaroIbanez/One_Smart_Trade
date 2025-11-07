"""CLI script for curating raw data."""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.logging import logger  # noqa: E402
from app.data.curation import DataCuration  # noqa: E402


def curate_interval(interval: str):
    """Curate data for a specific interval."""
    dc = DataCuration()

    logger.info(f"Curating {interval}...")
    result = dc.curate_timeframe(interval)

    if result.get("status") == "success":
        logger.info(f"✓ Successfully curated {interval}: {result.get('rows', 0)} rows")
        return True
    else:
        logger.error(f"✗ Failed to curate {interval}: {result.get('error', 'Unknown error')}")
        return False


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Curate raw market data")
    parser.add_argument(
        "--interval",
        choices=["15m", "30m", "1h", "4h", "1d", "1w", "all"],
        default="all",
        help="Timeframe to curate (default: all)"
    )

    args = parser.parse_args()

    intervals = ["15m", "30m", "1h", "4h", "1d", "1w"] if args.interval == "all" else [args.interval]

    results = []
    for interval in intervals:
        success = curate_interval(interval)
        results.append((interval, success))

    failed = [i for i, s in results if not s]
    if failed:
        logger.warning(f"Failed intervals: {', '.join(failed)}")
        sys.exit(1)
    else:
        logger.info("✓ All intervals curated successfully")
        sys.exit(0)


if __name__ == "__main__":
    main()

