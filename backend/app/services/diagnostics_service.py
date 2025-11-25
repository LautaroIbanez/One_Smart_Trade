"""Diagnostics service."""
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import settings
from app.core.database import SessionLocal
from app.data.curation import DataCuration
from app.data.ingestion import DataIngestion
from app.db.crud import get_last_run


class DiagnosticsService:
    """Service for system diagnostics."""

    async def get_last_run_info(self) -> dict[str, Any]:
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

    async def get_data_gaps(
        self,
        intervals: list[str] | None = None,
        lookback_days: int | None = None,
    ) -> dict[str, Any]:
        """
        Get data gaps for specified intervals.
        
        Args:
            intervals: List of intervals to check (default: ["1h", "1d"])
            lookback_days: Number of days to check (default: DATA_GAP_CHECK_LOOKBACK_DAYS)
            
        Returns:
            Dictionary with gap information for each interval
        """
        if intervals is None:
            intervals = ["1h", "1d"]
        
        if lookback_days is None:
            lookback_days = settings.DATA_GAP_CHECK_LOOKBACK_DAYS
        
        curation = DataCuration()
        ingestion = DataIngestion()
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=lookback_days)
        
        result: dict[str, Any] = {
            "generated_at": end_time.isoformat(),
            "lookback_days": lookback_days,
            "intervals": {},
        }
        
        for interval in intervals:
            try:
                # Get gaps
                gaps = ingestion.check_gaps(interval, start_time, end_time)
                
                # Get tolerance for this interval
                tolerance = curation._get_gap_tolerance_candles(interval)
                
                # Filter critical gaps (exceeding tolerance)
                critical_gaps = [gap for gap in gaps if gap.get("missing_candles", 0) > tolerance]
                total_missing = sum(gap.get("missing_candles", 0) for gap in critical_gaps)
                
                result["intervals"][interval] = {
                    "status": "ok" if not critical_gaps else "critical_gaps",
                    "tolerance_candles": tolerance,
                    "total_gaps": len(gaps),
                    "critical_gaps": len(critical_gaps),
                    "total_missing_candles": total_missing,
                    "gaps": gaps,
                    "critical_gaps_list": critical_gaps,
                }
            except Exception as e:
                result["intervals"][interval] = {
                    "status": "error",
                    "error": str(e),
                }
        
        return result

