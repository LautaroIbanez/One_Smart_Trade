"""Backtesting engine and metrics calculation."""

from .objectives import CalmarUnderDrawdown, Objective, ObjectiveConfig
from .optimizer import CampaignOptimizer, CandidateResult
from .pipeline import ValidationPipeline, WalkSegment
from .monitoring import PerformanceMonitor, RecalibrationEvent, statistical_significance_test
from .recalibration import AdaptiveCampaignOptimizer, RecalibrationJob
from .auto_shutdown import AutoShutdownManager, AutoShutdownPolicy, StrategyMetrics
from .risk import RuinSimulator
from .risk_sizing import AdaptiveRiskSizer, DrawdownController, RiskManager, RiskSizer
from .volatility_targeting import CombinedSizer, KellySizer, VolatilityTargeting
from .unified_risk_manager import RiskMetrics, UnifiedRiskManager
from .engine import (
    BacktestEngine,
    BacktestRunRequest,
    BacktestState,
    BacktestTemporalError,
    CandleSeries,
    InvalidSignalError,
    PartialFill,
    RiskManagedPositionSizer,
    StrategyProtocol,
    TradeFill,
)
from .persistence import (
    BacktestResultRepository,
    BacktestRunResult,
    save_backtest_result,
)
from .order_types import (
    BaseOrder,
    LimitOrder,
    MarketOrder,
    OrderConfig,
    OrderResult,
    OrderSide,
    OrderStatus,
    StopOrder,
)
from .position import Position, PositionConfig, PositionManager, PositionSide, PositionState
from .sensitivity import SensitivityRunner, SensitivityResult
from .validation import CampaignAbort, CampaignValidator, ValidationResult
from .walk_forward import TrainValOOSSplit, WalkForwardPipeline, WalkForwardResult, WalkForwardWindow
from .guardrails import CampaignRejectedReason, GuardrailChecker, GuardrailConfig, GuardrailResult
from .observability import CampaignMetrics, CampaignObservability
from .advanced_metrics import MetricsReport, calmar_penalized
from .ruin_simulation import RuinSimulationResult, monte_carlo_ruin
from .visualization import plot_parameter_distributions, plot_response_surface, plot_tornado_chart
from .trade_analytics import TradeAnalyticsRecord, TradeAnalyticsRepository

__all__ = [
    "CalmarUnderDrawdown",
    "Objective",
    "ObjectiveConfig",
    "CampaignOptimizer",
    "CandidateResult",
    "ValidationPipeline",
    "WalkSegment",
    "PerformanceMonitor",
    "RecalibrationEvent",
    "statistical_significance_test",
    "AdaptiveCampaignOptimizer",
    "RecalibrationJob",
    "SensitivityRunner",
    "SensitivityResult",
    "plot_tornado_chart",
    "plot_response_surface",
    "plot_parameter_distributions",
    "RiskSizer",
    "AdaptiveRiskSizer",
    "DrawdownController",
    "RiskManager",
    "RuinSimulator",
    "AutoShutdownPolicy",
    "AutoShutdownManager",
    "StrategyMetrics",
    "VolatilityTargeting",
    "KellySizer",
    "CombinedSizer",
    "UnifiedRiskManager",
    "RiskMetrics",
    "BaseOrder",
    "MarketOrder",
    "LimitOrder",
    "StopOrder",
    "OrderStatus",
    "OrderSide",
    "OrderConfig",
    "OrderResult",
    "Position",
    "PositionConfig",
    "PositionManager",
    "PositionSide",
    "PositionState",
    "ExecutionMetrics",
    "ExecutionTracker",
    "NoTradeEvent",
    "TrackingErrorMetrics",
    "calculate_tracking_error",
    "calculate_period_tracking_error",
    "ExecutionSimulator",
    "ExecutionSimulationResult",
    "StopRebalancer",
    "StopRebalanceEvent",
    "BacktestEngine",
    "BacktestRunRequest",
    "BacktestState",
    "BacktestTemporalError",
    "CandleSeries",
    "InvalidSignalError",
    "PartialFill",
    "RiskManagedPositionSizer",
    "StrategyProtocol",
    "TradeFill",
    "BacktestResultRepository",
    "BacktestRunResult",
    "save_backtest_result",
    "CampaignAbort",
    "CampaignValidator",
    "ValidationResult",
    "WalkForwardPipeline",
    "WalkForwardResult",
    "WalkForwardWindow",
    "TrainValOOSSplit",
    "CampaignRejectedReason",
    "GuardrailChecker",
    "GuardrailConfig",
    "GuardrailResult",
    "CampaignMetrics",
    "CampaignObservability",
    "MetricsReport",
    "calmar_penalized",
    "RuinSimulationResult",
    "monte_carlo_ruin",
    "TradeAnalyticsRecord",
    "TradeAnalyticsRepository",
]

