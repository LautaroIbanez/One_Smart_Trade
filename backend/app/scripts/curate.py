"""CLI script for curating raw data."""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.logging import logger  # noqa: E402
from app.data.curation import DataCuration  # noqa: E402


def curate_interval(
    interval: str,
    *,
    skip_quality: bool = False,
    skip_reconciler: bool = False,
    quality_config: dict | None = None,
):
    """
    Curate data for an interval with optional quality controls.

    Args:
        interval: Timeframe interval
        skip_quality: Skip statistical quality pipeline (default: False)
        skip_reconciler: Skip cross-venue reconciliation (default: False)
        quality_config: Quality pipeline configuration
    """
    dc = DataCuration(
        apply_quality=not skip_quality,
        apply_reconciler=not skip_reconciler,
        quality_config=quality_config or {},
    )

    logger.info(f"Curating {interval}...")
    result = dc.curate_timeframe(interval)

    if result.get("status") == "success":
        quality_stats = result.get("quality_stats", {})
        discrepancies = result.get("discrepancies")
        
        logger.info(f"✓ Successfully curated {interval}: {result.get('rows', 0)} rows")
        
        if quality_stats:
            logger.info(
                f"Quality pipeline applied: rows_before={quality_stats.get('rows_before')}, "
                f"rows_after={quality_stats.get('rows_after')}, "
                f"rows_removed={quality_stats.get('rows_removed')}"
            )
        
        if discrepancies:
            logger.info(
                f"Cross-venue discrepancies: count={discrepancies.get('count')}, "
                f"rate={discrepancies.get('rate', 0):.2%}"
            )
        
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
    parser.add_argument(
        "--skip-quality",
        action="store_true",
        help="Skip statistical quality pipeline (for debugging only)"
    )
    parser.add_argument(
        "--skip-reconciler",
        action="store_true",
        help="Skip cross-venue reconciliation"
    )

    args = parser.parse_args()

    intervals = ["15m", "30m", "1h", "4h", "1d", "1w"] if args.interval == "all" else [args.interval]

    results = []
    for interval in intervals:
        success = curate_interval(
            interval,
            skip_quality=args.skip_quality,
            skip_reconciler=args.skip_reconciler,
        )
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

