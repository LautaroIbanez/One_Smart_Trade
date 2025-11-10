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
    disclaimer: str


class SignalPerformancePoint(BaseModel):
    """Single realised recommendation performance record."""

    date: str
    signal: Literal["BUY", "HOLD", "SELL"]
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_price: float
    level_hit: str
    holding_days: int
    return_pct: float
    tracking_error: float
    hit_date: str | None = None
    signal_breakdown: dict = Field(default_factory=dict)


class SignalPerformanceResponse(BaseModel):
    """Aggregated signal performance response."""

    status: str
    timeline: list[SignalPerformancePoint]
    equity_curve: list[float]
    drawdown_curve: list[float]
    win_rate: float
    average_tracking_error: float
    trades_evaluated: int
