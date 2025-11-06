"""Diagnostics service."""
from typing import Dict, Any
from datetime import datetime
from app.core.database import SessionLocal
from app.db.crud import get_last_run


class DiagnosticsService:
    """Service for system diagnostics."""

    async def get_last_run_info(self) -> Dict[str, Any]:
        """Get last run information from database."""
        db = SessionLocal()
        try:
            last_ing = get_last_run(db, "ingestion")
            last_sig = get_last_run(db, "signal")
            return {
                "last_ingestion": last_ing.finished_at.isoformat() if last_ing else None,
                "last_signal": last_sig.finished_at.isoformat() if last_sig else None,
                "status": "ok",
            }
        finally:
            db.close()

