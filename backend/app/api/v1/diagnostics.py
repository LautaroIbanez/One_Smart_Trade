"""Diagnostics endpoints."""
from typing import List

from fastapi import APIRouter, Query

from app.services.diagnostics_service import DiagnosticsService

router = APIRouter()
diagnostics_service = DiagnosticsService()


@router.get("/last-run")
async def get_last_run():
    """Get information about the last recommendation calculation run."""
    return await diagnostics_service.get_last_run_info()


@router.get("/data-gaps")
async def get_data_gaps(
    intervals: List[str] | None = Query(None, description="Intervals to check (e.g., ['1h', '1d'])"),
    lookback_days: int | None = Query(None, description="Number of days to look back"),
):
    """
    Get data gaps for specified intervals.
    
    Returns gap information including:
    - Total gaps detected
    - Critical gaps (exceeding tolerance)
    - Missing candles count
    - Tolerance thresholds per interval
    """
    return await diagnostics_service.get_data_gaps(intervals=intervals, lookback_days=lookback_days)

