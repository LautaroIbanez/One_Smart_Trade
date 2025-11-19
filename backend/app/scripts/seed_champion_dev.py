"""Seed a default dev champion configuration for local development."""
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.database import SessionLocal
from app.db.crud import get_current_champion, record_champion_promotion
from app.core.logging import logger
from app.core.config import settings


def seed_dev_champion():
    """Seed a default dev champion if none exists."""
    with SessionLocal() as db:
        # Check if champion already exists
        existing = get_current_champion(db)
        if existing:
            logger.info(f"Champion already exists: {existing.params_id} (active={existing.is_active})")
            return existing
        
        # Only seed in dev/test environments
        env = os.getenv("ENV", "dev").lower()
        if env not in ("dev", "test", "development"):
            logger.warning(f"Not seeding champion in {env} environment. Set ENV=dev to seed.")
            return None
        
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


if __name__ == "__main__":
    try:
        champion = seed_dev_champion()
        if champion:
            print(f"✓ Dev champion seeded successfully: {champion.params_id}")
            sys.exit(0)
        else:
            print("⚠ No champion seeded (check environment or existing champion)")
            sys.exit(0)
    except Exception as e:
        logger.error(f"Failed to seed dev champion: {e}", exc_info=True)
        print(f"✗ Error seeding champion: {e}")
        sys.exit(1)

