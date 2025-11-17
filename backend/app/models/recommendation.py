"""Recommendation models."""
from typing import Literal

from pydantic import BaseModel, Field


class SignalType(str):
    """Signal type enum."""
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"


class EntryRange(BaseModel):
    """Entry range model."""
    min: float = Field(..., description="Minimum entry price")
    max: float = Field(..., description="Maximum entry price")
    optimal: float = Field(..., description="Optimal entry price")


class StopLossTakeProfit(BaseModel):
    """Stop loss and take profit levels."""
    stop_loss: float = Field(..., description="Stop loss price")
    take_profit: float = Field(..., description="Take profit price")
    stop_loss_pct: float = Field(..., description="Stop loss percentage")
    take_profit_pct: float = Field(..., description="Take profit percentage")


class Recommendation(BaseModel):
    """Trading recommendation model."""
    signal: Literal["BUY", "HOLD", "SELL"] = Field(..., description="Trading signal")
    entry_range: EntryRange = Field(..., description="Suggested entry range")
    stop_loss_take_profit: StopLossTakeProfit = Field(..., description="SL/TP levels")
    confidence: float = Field(..., ge=0, le=100, description="Confidence percentage")
    current_price: float = Field(..., description="Current BTC price")
    market_timestamp: str | None = Field(default=None, description="Timestamp of quoted spot price")
    spot_source: str | None = Field(default=None, description="Dataset used for current price (e.g., 1h)")
    analysis: str = Field(..., description="Professional textual analysis")
    indicators: dict = Field(default_factory=dict, description="Key technical indicators (RSI, MACD, ATR, etc.)")
    risk_metrics: dict = Field(default_factory=dict, description="Risk metrics (RR ratio, SL/TP probabilities, drawdown)")
    factors: dict = Field(default_factory=dict, description="Cross-timeframe factors (momentum alignment, volatility regime)")
    signal_breakdown: dict = Field(default_factory=dict, description="Strategy contributions and agreement metrics")
    timestamp: str = Field(..., description="ISO timestamp of recommendation")
    status: str = Field(default="closed", description="Current trade status (open|closed|inactive)")
    opened_at: str | None = Field(default=None, description="Timestamp when the trade was opened")
    closed_at: str | None = Field(default=None, description="Timestamp when the trade was closed")
    exit_reason: str | None = Field(default=None, description="Reason for closing the trade")
    exit_price: float | None = Field(default=None, description="Exit price when trade closed")
    exit_price_pct: float | None = Field(default=None, description="Return percentage realised at exit")
    signal_log_id: int | None = Field(default=None, description="ID of the signal_outcomes log entry")
    recommended_risk_fraction: float = Field(
        default=0.01,
        ge=0.0,
        le=1.0,
        description="Recommended risk fraction of equity (default: 0.01 = 1%)"
    )
    disclaimer: str = Field(
        default="This is not financial advice. Trading cryptocurrencies involves significant risk.",
        description="Legal disclaimer"
    )


class RecommendationResponse(BaseModel):
    """API response schema for recommendations with raw dictionaries."""

    signal: Literal["BUY", "HOLD", "SELL"]
    entry_range: dict
    stop_loss_take_profit: dict
    confidence: float
    current_price: float
    market_timestamp: str | None = None
    spot_source: str | None = None
    analysis: str
    indicators: dict
    risk_metrics: dict
    factors: dict = Field(default_factory=dict)
    signal_breakdown: dict = Field(default_factory=dict)
    timestamp: str
    status: str = Field(default="closed")
    opened_at: str | None = None
    closed_at: str | None = None
    exit_reason: str | None = None
    exit_price: float | None = None
    exit_price_pct: float | None = None
    signal_log_id: int | None = Field(
        default=None,
        description="ID of the signal_outcomes log entry linked to this recommendation",
    )
    recommended_risk_fraction: float = Field(
        default=0.01,
        ge=0.0,
        le=1.0,
        description="Recommended risk fraction of equity (default: 0.01 = 1%)"
    )
    disclaimer: str
    suggested_sizing: dict | None = Field(
        None,
        description="Suggested position sizing information (calculated with default parameters)",
    )


class SignalPerformancePoint(BaseModel):
    """Single realised recommendation performance record."""

    date: str
    signal: Literal["BUY", "HOLD", "SELL"]
    entry_price: float
    entry_price_realistic: float | None = None
    stop_loss: float
    take_profit: float
    exit_price: float
    exit_price_realistic: float | None = None
    level_hit: str
    holding_days: int
    return_pct: float
    return_pct_realistic: float | None = None
    tracking_error: float
    deviation_pct: float | None = None
    entry_slippage_pct: float | None = None
    exit_slippage_pct: float | None = None
    hit_date: str | None = None
    signal_breakdown: dict = Field(default_factory=dict)


class SignalPerformanceResponse(BaseModel):
    """Aggregated signal performance response."""

    status: str
    timeline: list[SignalPerformancePoint]
    equity_curve: list[float]  # Legacy: equals equity_theoretical
    equity_theoretical: list[float] | None = None
    equity_realistic: list[float] | None = None
    drawdown_curve: list[float]
    win_rate: float
    average_tracking_error: float
    trades_evaluated: int
    tracking_error_metrics: dict = Field(default_factory=dict)
