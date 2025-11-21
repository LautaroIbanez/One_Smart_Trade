"""
Script to seed initial data by running the daily pipeline.

This script can be used to populate an empty database with initial recommendations
and data, useful for:
- Setting up new environments
- Testing and development
- Recovery after data loss

Usage:
    poetry run python -m app.scripts.seed_initial_data
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path to allow imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.logging import setup_logging, logger
from app.main import job_daily_pipeline


async def main():
    """Run the daily pipeline to seed initial data."""
    setup_logging()
    
    logger.info("Starting initial data seeding via daily pipeline")
    
    try:
        await job_daily_pipeline()
        logger.info("Initial data seeding completed successfully")
        return 0
    except Exception as exc:
        logger.error(f"Initial data seeding failed: {exc}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

