"""Diagnostics endpoints."""
from fastapi import APIRouter
from app.services.diagnostics_service import DiagnosticsService

router = APIRouter()
diagnostics_service = DiagnosticsService()


@router.get("/last-run")
async def get_last_run():
    """Get information about the last recommendation calculation run."""
    return await diagnostics_service.get_last_run_info()

