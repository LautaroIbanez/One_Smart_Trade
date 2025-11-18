"""Recommendation models."""
from typing import Literal, Any

from pydantic import BaseModel, Field


class ConfidenceBand(BaseModel):
    """Historical confidence interval for calibrated scores."""

    lower: float = Field(..., ge=0.0, le=100.0)
    upper: float = Field(..., ge=0.0, le=100.0)
    source: str | None = Field(default=None, description="Calibrator or regime reference")
    note: str | None = Field(default=None, description="Additional context for the band")


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
    confidence: float = Field(..., ge=0, le=100, description="Legacy confidence percentage (raw score)")
    confidence_raw: float = Field(..., ge=0, le=100, description="Raw confidence before calibration")
    confidence_calibrated: float | None = Field(default=None, ge=0, le=100, description="Calibrated confidence percentage")
    confidence_band: ConfidenceBand | None = Field(default=None, description="Historical hit-rate interval for the calibrated score")
    current_price: float = Field(..., description="Current BTC price")
    market_timestamp: str | None = Field(default=None, description="Timestamp of quoted spot price")
    spot_source: str | None = Field(default=None, description="Dataset used for current price (e.g., 1h)")
    analysis: str = Field(..., description="Professional textual analysis")
    indicators: dict = Field(default_factory=dict, description="Key technical indicators (RSI, MACD, ATR, etc.)")
    risk_metrics: dict = Field(default_factory=dict, description="Risk metrics (RR ratio, SL/TP probabilities, drawdown)")
    factors: dict = Field(default_factory=dict, description="Cross-timeframe factors (momentum alignment, volatility regime)")
    signal_breakdown: dict = Field(default_factory=dict, description="Strategy contributions and agreement metrics")
    calibration_metadata: dict | None = Field(default=None, description="Metadata about the calibrator used")
    timestamp: str = Field(..., description="ISO timestamp of recommendation")
    status: str = Field(default="closed", description="Current trade status (open|closed|inactive)")
    opened_at: str | None = Field(default=None, description="Timestamp when the trade was opened")
    closed_at: str | None = Field(default=None, description="Timestamp when the trade was closed")
    exit_reason: str | None = Field(default=None, description="Reason for closing the trade")
    exit_price: float | None = Field(default=None, description="Exit price when trade closed")
    exit_price_pct: float | None = Field(default=None, description="Return percentage realised at exit")
    signal_log_id: int | None = Field(default=None, description="ID of the signal_outcomes log entry")
    confidence_calibrated: float | None = Field(default=None, description="Calibrated confidence percentage")
    recommended_risk_fraction: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Recommended risk fraction of equity (None if sizing unavailable or requires capital input)"
    )
    recommended_position_size: float | None = Field(
        default=None,
        description="Recommended position size in units (calculated from user portfolio if available)"
    )
    risk_pct: float | None = Field(
        default=None,
        description="Effective risk percentage after drawdown adjustment"
    )
    capital_assumed: float | None = Field(
        default=None,
        description="Capital amount used for sizing calculation (user equity or default assumption)"
    )
    disclaimer: str = Field(
        default="This is not financial advice. Trading cryptocurrencies involves significant risk.",
        description="Legal disclaimer"
    )


class ExecutionPlan(BaseModel):
    """Manual execution playbook for trading recommendations."""
    
    operational_window: dict = Field(..., description="Time window for executing the trade")
    order_type: str = Field(..., description="Recommended order type (limit, market, stop)")
    suggested_size: dict = Field(..., description="Suggested position size based on minimum capital")
    instructions: str = Field(..., description="Step-by-step execution instructions")
    minimum_capital_required: float | None = Field(None, description="Minimum capital required in USD")
    risk_per_trade_pct: float | None = Field(None, description="Risk percentage per trade")
    notes: list[str] = Field(default_factory=list, description="Additional execution notes and warnings")


class RecommendationResponse(BaseModel):
    """API response schema for recommendations with raw dictionaries."""

    signal: Literal["BUY", "HOLD", "SELL"]
    entry_range: dict
    stop_loss_take_profit: dict
    confidence: float
    confidence_raw: float
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
    confidence_calibrated: float | None = Field(
        default=None,
        description="Calibrated confidence percentage (0-100)",
    )
    confidence_band: ConfidenceBand | None = Field(
        default=None,
        description="Historical hit-rate interval for the calibrated score",
    )
    calibration_metadata: dict | None = Field(
        default=None,
        description="Metadata about the calibrator used (regime, metrics)",
    )
    recommended_risk_fraction: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Recommended risk fraction of equity (None if sizing unavailable or requires capital input)"
    )
    recommended_position_size: float | None = Field(
        default=None,
        description="Recommended position size in units (calculated from user portfolio if available)"
    )
    risk_pct: float | None = Field(
        default=None,
        description="Effective risk percentage after drawdown adjustment"
    )
    capital_assumed: float | None = Field(
        default=None,
        description="Capital amount used for sizing calculation (user equity or default assumption)"
    )
    tracking_error_rmse: float | None = Field(None, description="Tracking error RMSE (Root Mean Squared Error)")
    tracking_error_max: float | None = Field(None, description="Maximum tracking error (basis points)")
    backtest_run_id: str | None = Field(None, description="Backtest run ID for traceability")
    backtest_cagr: float | None = Field(None, description="Backtest CAGR (Compound Annual Growth Rate) percentage")
    backtest_win_rate: float | None = Field(None, description="Backtest win rate percentage")
    backtest_risk_reward_ratio: float | None = Field(None, description="Backtest risk/reward ratio")
    backtest_max_drawdown: float | None = Field(None, description="Backtest maximum drawdown percentage")
    backtest_slippage_bps: float | None = Field(None, description="Backtest average slippage in basis points")
    tracking_error_bps: float | None = Field(None, description="Tracking error in basis points (difference between target SL/TP and actual exit price)")
    orderbook_fallback_events: int | None = Field(None, description="Number of orderbook fallback events")
    disclaimer: str
    suggested_sizing: dict | None = Field(
        None,
        description="Suggested position sizing information (calculated with user portfolio data when available)",
    )
    execution_plan: dict | None = Field(
        None,
        description="Manual execution playbook with operational window, order type, sizing, and instructions",
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


class HistorySparklinePoint(BaseModel):
    """Point for sparkline visualisation."""

    timestamp: str
    theoretical: float
    realistic: float


class HistoryInsights(BaseModel):
    """Additional analytics for recommendation history."""

    sparkline_series: dict[str, list[HistorySparklinePoint]] = Field(default_factory=dict)
    stats: dict[str, float] = Field(default_factory=dict)


class RecommendationHistoryItem(BaseModel):
    """Single entry in paginated recommendation history."""

    id: int
    timestamp: str
    date: str
    signal: Literal["BUY", "HOLD", "SELL"]
    status: str
    execution_status: str
    exit_reason: str | None = None
    entry_price: float | None = None
    exit_price: float | None = None
    return_pct: float | None = None
    theoretical_return_pct: float | None = None
    realistic_return_pct: float | None = None
    tracking_error_pct: float | None = None
    tracking_error_bps: float | None = None
    divergence_flag: bool = False
    code_commit: str | None = None
    dataset_version: str | None = None
    ingestion_timestamp: str | None = None
    seed: int | None = None
    params_digest: str | None = None
    config_version: str | None = None
    snapshot_url: str | None = None
    risk_metrics: dict[str, Any] | None = None
    backtest_run_id: str | None = None
    backtest_cagr: float | None = None
    backtest_win_rate: float | None = None
    backtest_risk_reward_ratio: float | None = None
    backtest_max_drawdown: float | None = None
    backtest_slippage_bps: float | None = None
    tracking_error_bps: float | None = None


class RecommendationHistoryResponse(BaseModel):
    """Paginated recommendation history response."""

    items: list[RecommendationHistoryItem]
    next_cursor: str | None = None
    has_more: bool = False
    filters: dict[str, Any] = Field(default_factory=dict)
    insights: HistoryInsights | None = None
    download_url: str | None = None
