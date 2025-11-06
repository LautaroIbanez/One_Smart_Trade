"""Recommendation models."""
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


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
    analysis: str = Field(..., description="Professional textual analysis")
    indicators: dict = Field(default_factory=dict, description="Key technical indicators (RSI, MACD, ATR, etc.)")
    risk_metrics: dict = Field(default_factory=dict, description="Risk metrics (RR ratio, SL/TP probabilities, drawdown)")
    factors: dict = Field(default_factory=dict, description="Cross-timeframe factors (momentum alignment, volatility regime)")
    timestamp: str = Field(..., description="ISO timestamp of recommendation")
    disclaimer: str = Field(
        default="This is not financial advice. Trading cryptocurrencies involves significant risk.",
        description="Legal disclaimer"
    )

