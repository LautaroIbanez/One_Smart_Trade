"""Performance endpoints."""
from fastapi import APIRouter
from app.services.performance_service import PerformanceService

router = APIRouter()
performance_service = PerformanceService()


@router.get("/summary")
async def get_performance_summary():
    """Get backtesting performance summary with metrics and disclaimer."""
    result = await performance_service.get_summary()
    result["disclaimer"] = "This is not financial advice. Backtesting results do not guarantee future performance. Trading cryptocurrencies involves significant risk."
    return result

