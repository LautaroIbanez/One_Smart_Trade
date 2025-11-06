"""Performance endpoints."""
from fastapi import APIRouter
from app.services.performance_service import PerformanceService

router = APIRouter()
performance_service = PerformanceService()


@router.get("/summary")
async def get_performance_summary():
    """Get backtesting performance summary."""
    return await performance_service.get_summary()

