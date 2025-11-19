"""Seed a default dev champion configuration for local development.

This script can be executed in two ways:
1. As a module: `python -m app.scripts.seed_champion_dev` (from backend directory)
2. Directly: `python backend/app/scripts/seed_champion_dev.py` (from repo root)

The script will only seed champions in dev/test/development environments.
"""
import os
import sys
from pathlib import Path

# Ensure app package is importable
# Try importing first; if it fails, add backend to path (for direct execution)
try:
    import app.core.database  # noqa: F401
except ImportError:
    # When running directly, add backend to path
    backend_dir = Path(__file__).resolve().parent.parent.parent
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

from app.core.database import SessionLocal, Base, engine  # noqa: E402
from app.db.crud import get_current_champion, record_champion_promotion  # noqa: E402
from app.core.logging import logger  # noqa: E402
from app.core.config import settings  # noqa: E402


def seed_dev_champion():
    """
    Seed a default dev champion if none exists.
    
    This function will only seed champions in dev/test/development environments.
    In production, it will refuse to seed and return None.
    
    Returns:
        StrategyChampionORM if champion exists or was seeded, None otherwise
    """
    # Check environment first (before any DB operations)
    env = os.getenv("ENV", "dev").lower()
    if env not in ("dev", "test", "development"):
        logger.warning(
            f"Not seeding champion in {env} environment. Set ENV=dev to seed.",
            extra={"environment": env},
        )
        return None
    
    # Ensure tables exist (for SQLite dev databases)
    # In production, tables should be created via Alembic migrations
    if "sqlite" in settings.DATABASE_URL.lower():
        try:
            Base.metadata.create_all(bind=engine, checkfirst=True)
            logger.debug("Database tables verified/created")
        except Exception as e:
            logger.warning(f"Could not create tables (may already exist): {e}")
    
    with SessionLocal() as db:
        # Check if champion already exists
        existing = get_current_champion(db)
        if existing:
            logger.info(
                f"Champion already exists: {existing.params_id} (active={existing.is_active})",
                extra={"champion_id": existing.id, "params_id": existing.params_id},
            )
            return existing
        
        logger.info("Seeding default dev champion configuration...")
        
        # Create a minimal dev champion config
        champion_record = {
            "params_id": "dev-default",
            "params_version": "1.0.0",
            "objective": "maximize_sharpe",
            "target_metric": "sharpe_ratio",
            "target_value": 1.0,
            "score": 0.5,  # Placeholder score
            "metrics": {
                "sharpe_ratio": 0.5,
                "win_rate": 0.55,
                "max_drawdown_pct": 15.0,
                "cagr": 10.0,
            },
            "engine_args": {
                "commission_rate": 0.001,
                "slippage_bps": 5.0,
                "initial_capital": 10000.0,
            },
            "execution_overrides": {},
            "drawdown_limit": 20.0,
        }
        
        champion = record_champion_promotion(db, champion_record)
        logger.info(f"✓ Seeded dev champion: {champion.params_id} (ID: {champion.id})")
        return champion


def main() -> int:
    """
    Main entry point for seeding dev champion.
    
    Returns:
        Exit code: 0 on success, 1 on error
    """
    try:
        champion = seed_dev_champion()
        if champion:
            print(f"✓ Dev champion seeded successfully: {champion.params_id}")
            return 0
        else:
            print("⚠ No champion seeded (check environment or existing champion)")
            return 0
    except Exception as e:
        logger.error(f"Failed to seed dev champion: {e}", exc_info=True)
        print(f"✗ Error seeding champion: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

