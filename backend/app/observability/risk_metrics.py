"""Risk management Prometheus metrics."""
from prometheus_client import Gauge, Counter

# Current drawdown metrics
RISK_CURRENT_DRAWDOWN = Gauge(
    "risk_current_drawdown_pct",
    "Current drawdown percentage",
    ["strategy", "asset"],
)

RISK_PEAK_EQUITY = Gauge(
    "risk_peak_equity",
    "Peak equity value",
    ["strategy", "asset"],
)

RISK_CURRENT_EQUITY = Gauge(
    "risk_current_equity",
    "Current equity value",
    ["strategy", "asset"],
)

# Risk of ruin
RISK_OF_RUIN = Gauge(
    "risk_risk_of_ruin",
    "Estimated risk of ruin probability (0.0 to 1.0)",
    ["strategy", "asset", "threshold"],
)

# Suggested position sizing
RISK_SUGGESTED_FRACTION = Gauge(
    "risk_suggested_fraction",
    "Suggested position size as fraction of equity",
    ["strategy", "asset"],
)

# Risk budget metrics
RISK_BUDGET_PCT = Gauge(
    "risk_budget_pct",
    "Risk budget as percentage of capital",
    ["strategy", "asset"],
)

RISK_EFFECTIVE_BUDGET_PCT = Gauge(
    "risk_effective_budget_pct",
    "Effective risk budget after drawdown adjustment",
    ["strategy", "asset"],
)

# Shutdown status
RISK_SHUTDOWN_ACTIVE = Gauge(
    "risk_shutdown_active",
    "Whether trading shutdown is active (1=active, 0=inactive)",
    ["strategy", "asset"],
)

RISK_SIZE_REDUCTION_ACTIVE = Gauge(
    "risk_size_reduction_active",
    "Whether size reduction is active (1=active, 0=inactive)",
    ["strategy", "asset"],
)

RISK_SIZE_REDUCTION_FACTOR = Gauge(
    "risk_size_reduction_factor",
    "Size reduction multiplier (0.0 to 1.0)",
    ["strategy", "asset"],
)

# Alert threshold for risk of ruin
RUIN_ALERT_THRESHOLD = 0.05  # 5%

def update_risk_metrics(
    strategy: str,
    asset: str,
    current_drawdown_pct: float,
    peak_equity: float,
    current_equity: float,
    risk_of_ruin: float,
    suggested_fraction: float,
    risk_budget_pct: float,
    effective_budget_pct: float,
    shutdown_active: bool,
    size_reduction_active: bool,
    size_reduction_factor: float,
    threshold: str = "0.5",
) -> dict[str, bool]:
    """
    Update all risk metrics for a strategy/asset.
    
    Args:
        strategy: Strategy name
        asset: Asset symbol
        current_drawdown_pct: Current drawdown percentage
        peak_equity: Peak equity value
        current_equity: Current equity value
        risk_of_ruin: Estimated risk of ruin (0.0 to 1.0)
        suggested_fraction: Suggested position size fraction
        risk_budget_pct: Base risk budget percentage
        effective_budget_pct: Effective risk budget after adjustments
        shutdown_active: Whether shutdown is active
        size_reduction_active: Whether size reduction is active
        size_reduction_factor: Size reduction multiplier
        threshold: Ruin threshold label (e.g., "0.5" for -50%)
        
    Returns:
        Dict with alert flags (e.g., {"ruin_alert": True})
    """
    # Update drawdown metrics
    RISK_CURRENT_DRAWDOWN.labels(strategy=strategy, asset=asset).set(current_drawdown_pct)
    RISK_PEAK_EQUITY.labels(strategy=strategy, asset=asset).set(peak_equity)
    RISK_CURRENT_EQUITY.labels(strategy=strategy, asset=asset).set(current_equity)
    
    # Update risk of ruin
    RISK_OF_RUIN.labels(strategy=strategy, asset=asset, threshold=threshold).set(risk_of_ruin)
    
    # Update suggested fraction
    RISK_SUGGESTED_FRACTION.labels(strategy=strategy, asset=asset).set(suggested_fraction)
    
    # Update risk budget metrics
    RISK_BUDGET_PCT.labels(strategy=strategy, asset=asset).set(risk_budget_pct)
    RISK_EFFECTIVE_BUDGET_PCT.labels(strategy=strategy, asset=asset).set(effective_budget_pct)
    
    # Update shutdown status
    RISK_SHUTDOWN_ACTIVE.labels(strategy=strategy, asset=asset).set(1.0 if shutdown_active else 0.0)
    RISK_SIZE_REDUCTION_ACTIVE.labels(strategy=strategy, asset=asset).set(1.0 if size_reduction_active else 0.0)
    RISK_SIZE_REDUCTION_FACTOR.labels(strategy=strategy, asset=asset).set(size_reduction_factor)
    
    # Check for alerts
    alerts = {
        "ruin_alert": risk_of_ruin >= RUIN_ALERT_THRESHOLD,
        "shutdown_alert": shutdown_active,
        "size_reduction_alert": size_reduction_active,
    }
    
    return alerts


# User-level risk metrics
USER_RISK_REJECTIONS_TOTAL = Counter(
    "user_risk_rejections_total",
    "Total number of risk-based rejections for user",
    ["user_id", "rejection_type"],  # rejection_type: missing_equity, ruin_risk_too_high, risk_blocked, exposure_limit_exceeded
)

USER_RUIN_PROBABILITY = Gauge(
    "user_ruin_probability",
    "Current risk of ruin probability for user",
    ["user_id"],
)

USER_EXPOSURE_RATIO = Gauge(
    "user_exposure_ratio",
    "Current exposure ratio (beta-adjusted notional / equity) for user",
    ["user_id"],
)

USER_EXPOSURE_LIMIT_ALERT = Gauge(
    "user_exposure_limit_alert",
    "Alert flag when user exposure exceeds 80% of limit (1 = alert active, 0 = no alert)",
    ["user_id"],
)

# Daily risk metrics
USER_DAILY_RISK_PCT = Gauge(
    "user_risk_daily_pct",
    "Daily committed risk as percentage of equity",
    ["user_id"],
)

USER_DAILY_RISK_WARNING = Gauge(
    "user_risk_daily_warning",
    "Hard warning flag when daily risk exceeds 2% (1 = warning active, 0 = no warning)",
    ["user_id"],
)

# Counter for repeated daily risk warnings (for alerting on patterns)
USER_DAILY_RISK_WARNINGS_TOTAL = Counter(
    "user_risk_daily_warnings_total",
    "Total number of times daily risk warning threshold (2%) was exceeded",
    ["user_id"],
)

# Counter for daily risk limit blocks
USER_DAILY_RISK_BLOCKS_TOTAL = Counter(
    "user_risk_daily_blocks_total",
    "Total number of times daily risk limit (3%) was exceeded and blocked",
    ["user_id"],
)



