"""Pydantic models for performance API responses."""
from typing import Optional

from pydantic import BaseModel, Field


class RollingMetrics(BaseModel):
    """Rolling metrics over a time window."""
    avg_return: float = Field(..., description="Average return percentage")
    avg_sharpe: float = Field(..., description="Average Sharpe ratio")
    max_dd: float = Field(..., description="Maximum drawdown percentage")


class PerformanceMetrics(BaseModel):
    """Comprehensive performance metrics."""
    cagr: float = Field(..., description="Compound Annual Growth Rate (%)")
    sharpe: float = Field(..., description="Sharpe Ratio (annualized)")
    sortino: float = Field(..., description="Sortino Ratio (annualized)")
    max_drawdown: float = Field(..., description="Maximum Drawdown (%)")
    win_rate: float = Field(..., description="Win Rate (%)")
    profit_factor: float = Field(..., description="Profit Factor")
    expectancy: float = Field(..., description="Expectancy ($)")
    calmar: float = Field(..., description="Calmar Ratio")
    total_return: float = Field(..., description="Total Return (%)")
    total_trades: int = Field(..., description="Total number of trades")
    winning_trades: int = Field(..., description="Number of winning trades")
    losing_trades: int = Field(..., description="Number of losing trades")
    rolling_monthly: Optional[RollingMetrics] = Field(None, description="Rolling monthly metrics")
    rolling_quarterly: Optional[RollingMetrics] = Field(None, description="Rolling quarterly metrics")


class PerformancePeriod(BaseModel):
    """Backtest period."""
    start: str = Field(..., description="Start date (ISO format)")
    end: str = Field(..., description="End date (ISO format)")


class PerformanceSummaryResponse(BaseModel):
    """Performance summary API response."""
    status: str = Field(..., description="Status: success or error")
    metrics: Optional[PerformanceMetrics] = Field(None, description="Performance metrics")
    period: Optional[PerformancePeriod] = Field(None, description="Backtest period")
    report_path: Optional[str] = Field(None, description="Path to generated report")
    message: Optional[str] = Field(None, description="Error message if status is error")
    disclaimer: str = Field(
        default="This is not financial advice. Backtesting results do not guarantee future performance. Trading cryptocurrencies involves significant risk.",
        description="Legal disclaimer"
    )

