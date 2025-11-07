"""CLI script for manually regenerating signals."""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.logging import logger  # noqa: E402
from app.main import job_generate_signal  # noqa: E402


def main():
    """CLI entry point."""
    logger.info("Manually triggering signal generation...")

    try:
        asyncio.run(job_generate_signal())
        logger.info("✓ Signal generation completed")
        sys.exit(0)
    except Exception as e:
        logger.error(f"✗ Signal generation failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

