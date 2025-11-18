"""Pydantic models for performance API responses."""
from typing import Optional

from pydantic import BaseModel, Field


class RollingMetrics(BaseModel):
    """Rolling metrics over a time window."""

    avg_return: float = Field(..., description="Average return percentage")
    avg_sharpe: float = Field(..., description="Average Sharpe ratio")
    max_dd: float = Field(..., description="Maximum drawdown percentage")


class RiskProfile(BaseModel):
    """Monte Carlo risk profile metrics."""

    median_worst_dd_pct: float = Field(0.0, description="Median worst drawdown (%) across simulations")
    p95_worst_dd_pct: float = Field(0.0, description="95th percentile worst drawdown (%)")
    p99_worst_dd_pct: float = Field(0.0, description="99th percentile worst drawdown (%)")
    ruin_prob: float = Field(0.0, description="Probability of ruin (capital below threshold)")
    median_losing_streak: int = Field(0, description="Median losing streak length (trades)")
    p95_losing_streak: int = Field(0, description="95th percentile losing streak length (trades)")
    p99_losing_streak: int = Field(0, description="99th percentile losing streak length (trades)")
    prob_streak_ge_threshold: float = Field(0.0, description="Probability of losing streak >= threshold")
    streak_threshold: int = Field(0, description="Losing streak risk threshold (trades)")
    trials: int = Field(0, description="Number of Monte Carlo trials")
    horizon_trades: int = Field(0, description="Number of simulated trades per trial")
    ruin_threshold: float = Field(0.0, description="Capital ratio considered ruin")
    streak_risk_threshold: int = Field(0, description="Configured streak threshold used in probability")


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
    risk_profile: Optional[RiskProfile] = Field(None, description="Monte Carlo risk metrics")
    tracking_error_rmse: Optional[float] = Field(None, description="Tracking error RMSE (Root Mean Squared Error)")
    tracking_error_max: Optional[float] = Field(None, description="Maximum tracking error (basis points)")
    orderbook_fallback_events: Optional[int] = Field(None, description="Number of orderbook fallback events")


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
    tracking_error_rmse: Optional[float] = Field(None, description="Tracking error RMSE")
    tracking_error_max: Optional[float] = Field(None, description="Maximum tracking error (bps)")
    orderbook_fallback_events: Optional[int] = Field(None, description="Number of orderbook fallback events")
    has_realistic_data: bool = Field(default=False, description="Whether backtest includes realistic execution data")
    tracking_error_metrics: Optional[dict] = Field(None, description="Detailed tracking error diagnostics")
    tracking_error_series: Optional[list[dict]] = Field(None, description="Tracking error time series")
    tracking_error_cumulative: Optional[list[dict]] = Field(None, description="Cumulative tracking error series")
    chart_banners: Optional[list[str]] = Field(None, description="Warnings shown on performance charts")
    disclaimer: str = Field(
        default="This is not financial advice. Backtesting results do not guarantee future performance. Trading cryptocurrencies involves significant risk.",
        description="Legal disclaimer",
    )

