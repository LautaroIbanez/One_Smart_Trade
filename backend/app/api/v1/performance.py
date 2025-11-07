"""Performance endpoints."""
from fastapi import APIRouter, HTTPException

from app.models.performance import (
    PerformanceMetrics,
    PerformancePeriod,
    PerformanceSummaryResponse,
    RollingMetrics,
)
from app.services.performance_service import PerformanceService

router = APIRouter()
performance_service = PerformanceService()


@router.get("/summary", response_model=PerformanceSummaryResponse)
async def get_performance_summary():
    """
    Get backtesting performance summary with metrics and disclaimer.

    Returns comprehensive metrics including CAGR, Sharpe, Sortino, Max Drawdown,
    Win Rate, Profit Factor, Expectancy, Calmar, and rolling KPIs (monthly/quarterly).
    """
    try:
        result = await performance_service.get_summary()

        if result.get("status") == "error":
            return PerformanceSummaryResponse(
                status="error",
                message=result.get("message", "Unknown error"),
                metrics=None,
                period=None,
                report_path=None,
            )

        metrics_dict = result.get("metrics", {})
        rolling_monthly = metrics_dict.get("rolling_monthly")
        rolling_quarterly = metrics_dict.get("rolling_quarterly")

        metrics = PerformanceMetrics(
            cagr=metrics_dict.get("cagr", 0.0),
            sharpe=metrics_dict.get("sharpe", 0.0),
            sortino=metrics_dict.get("sortino", 0.0),
            max_drawdown=metrics_dict.get("max_drawdown", 0.0),
            win_rate=metrics_dict.get("win_rate", 0.0),
            profit_factor=metrics_dict.get("profit_factor", 0.0),
            expectancy=metrics_dict.get("expectancy", 0.0),
            calmar=metrics_dict.get("calmar", 0.0),
            total_return=metrics_dict.get("total_return", 0.0),
            total_trades=metrics_dict.get("total_trades", 0),
            winning_trades=metrics_dict.get("winning_trades", 0),
            losing_trades=metrics_dict.get("losing_trades", 0),
            rolling_monthly=RollingMetrics(**rolling_monthly) if rolling_monthly else None,
            rolling_quarterly=RollingMetrics(**rolling_quarterly) if rolling_quarterly else None,
        )

        period_dict = result.get("period", {})
        period = PerformancePeriod(
            start=period_dict.get("start", ""),
            end=period_dict.get("end", ""),
        ) if period_dict else None

        return PerformanceSummaryResponse(
            status="success",
            metrics=metrics,
            period=period,
            report_path=result.get("report_path"),
            message=None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

