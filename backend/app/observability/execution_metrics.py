"""Prometheus metrics for execution and tracking error monitoring."""
from prometheus_client import Counter, Gauge, Histogram

# Execution metrics
EXECUTION_SLIPPAGE_REAL_BPS = Histogram(
    "execution_slippage_real_bps",
    "Realized slippage in basis points",
    ["symbol", "side", "order_type"],
    buckets=[0, 5, 10, 20, 50, 100, 200, 500, 1000],
)

EXECUTION_FILL_RATE = Gauge(
    "execution_fill_rate",
    "Order fill rate (0-1)",
    ["symbol", "order_type"],
)

EXECUTION_PARTIAL_FILL_RATE = Gauge(
    "execution_partial_fill_rate",
    "Partial fill rate (0-1)",
    ["symbol", "order_type"],
)

EXECUTION_CANCEL_RATIO = Gauge(
    "execution_cancel_ratio",
    "Order cancellation ratio (0-1)",
    ["symbol", "order_type"],
)

EXECUTION_NO_TRADE_RATIO = Gauge(
    "execution_no_trade_ratio",
    "No-trade ratio (0-1)",
    ["symbol", "order_type"],
)

EXECUTION_AVG_WAIT_BARS = Histogram(
    "execution_avg_wait_bars",
    "Average wait time in bars",
    ["symbol", "order_type"],
    buckets=[0, 1, 2, 3, 5, 10, 20, 50],
)

EXECUTION_OPPORTUNITY_COST = Counter(
    "execution_opportunity_cost_total",
    "Total opportunity cost from missed trades",
    ["symbol"],
)

# Tracking error metrics
TRACKING_ERROR_MEAN_DEVIATION = Gauge(
    "tracking_error_mean_deviation",
    "Mean tracking error (realistic - theoretical)",
    ["symbol", "campaign_id"],
)

TRACKING_ERROR_MAX_DIVERGENCE = Gauge(
    "tracking_error_max_divergence",
    "Maximum absolute divergence between curves",
    ["symbol", "campaign_id"],
)

TRACKING_ERROR_CORRELATION = Gauge(
    "tracking_error_correlation",
    "Correlation between theoretical and realistic equity curves",
    ["symbol", "campaign_id"],
)

TRACKING_ERROR_RMSE = Gauge(
    "tracking_error_rmse",
    "Root Mean Squared Error of tracking error",
    ["symbol", "campaign_id"],
)

TRACKING_ERROR_TRACKING_SHARPE = Gauge(
    "tracking_error_tracking_sharpe",
    "Tracking Sharpe ratio (annualized)",
    ["symbol", "campaign_id"],
)

TRACKING_ERROR_CUMULATIVE = Gauge(
    "tracking_error_cumulative",
    "Cumulative tracking error at end of period",
    ["symbol", "campaign_id"],
)

# Alert thresholds
TRACKING_ERROR_DEVIATION_THRESHOLD = 0.05  # 5% deviation triggers alert
TRACKING_ERROR_ALERT_COUNT = Counter(
    "tracking_error_alerts_total",
    "Total alerts for excessive tracking error deviation",
    ["symbol", "campaign_id", "threshold"],
)


def update_execution_metrics(
    symbol: str,
    order_type: str,
    *,
    slippage_bps: float | None = None,
    fill_rate: float | None = None,
    partial_fill_rate: float | None = None,
    cancel_ratio: float | None = None,
    no_trade_ratio: float | None = None,
    avg_wait_bars: float | None = None,
    opportunity_cost: float | None = None,
    side: str | None = None,
) -> None:
    """
    Update execution metrics in Prometheus.
    
    Args:
        symbol: Trading symbol
        order_type: Order type (market, limit, stop)
        slippage_bps: Realized slippage in basis points
        fill_rate: Fill rate (0-1)
        partial_fill_rate: Partial fill rate (0-1)
        cancel_ratio: Cancellation ratio (0-1)
        no_trade_ratio: No-trade ratio (0-1)
        avg_wait_bars: Average wait time in bars
        opportunity_cost: Opportunity cost from missed trades
        side: Order side (buy/sell)
    """
    labels = {"symbol": symbol, "order_type": order_type}
    
    if slippage_bps is not None and side is not None:
        EXECUTION_SLIPPAGE_REAL_BPS.labels(symbol=symbol, side=side, order_type=order_type).observe(
            abs(slippage_bps)
        )
    
    if fill_rate is not None:
        EXECUTION_FILL_RATE.labels(**labels).set(fill_rate)
    
    if partial_fill_rate is not None:
        EXECUTION_PARTIAL_FILL_RATE.labels(**labels).set(partial_fill_rate)
    
    if cancel_ratio is not None:
        EXECUTION_CANCEL_RATIO.labels(**labels).set(cancel_ratio)
    
    if no_trade_ratio is not None:
        EXECUTION_NO_TRADE_RATIO.labels(**labels).set(no_trade_ratio)
    
    if avg_wait_bars is not None:
        EXECUTION_AVG_WAIT_BARS.labels(**labels).observe(avg_wait_bars)
    
    if opportunity_cost is not None and opportunity_cost > 0:
        EXECUTION_OPPORTUNITY_COST.labels(symbol=symbol).inc(opportunity_cost)


def update_tracking_error_metrics(
    symbol: str,
    campaign_id: str,
    tracking_error: dict[str, float],
    *,
    threshold_pct: float = TRACKING_ERROR_DEVIATION_THRESHOLD,
) -> list[dict[str, str]]:
    """
    Update tracking error metrics and check for alerts.
    
    Args:
        symbol: Trading symbol
        campaign_id: Campaign identifier
        tracking_error: Tracking error metrics dict
        threshold_pct: Deviation threshold for alerts (default: 5%)
        
    Returns:
        List of alert dicts if threshold exceeded
    """
    labels = {"symbol": symbol, "campaign_id": campaign_id}
    
    # Update metrics
    if "mean_deviation" in tracking_error:
        TRACKING_ERROR_MEAN_DEVIATION.labels(**labels).set(tracking_error["mean_deviation"])
    
    if "max_divergence" in tracking_error:
        TRACKING_ERROR_MAX_DIVERGENCE.labels(**labels).set(tracking_error["max_divergence"])
    
    if "correlation" in tracking_error:
        TRACKING_ERROR_CORRELATION.labels(**labels).set(tracking_error["correlation"])
    
    if "rmse" in tracking_error:
        TRACKING_ERROR_RMSE.labels(**labels).set(tracking_error["rmse"])
    
    if "tracking_sharpe" in tracking_error:
        TRACKING_ERROR_TRACKING_SHARPE.labels(**labels).set(tracking_error["tracking_sharpe"])
    
    if "cumulative_tracking_error" in tracking_error:
        TRACKING_ERROR_CUMULATIVE.labels(**labels).set(tracking_error["cumulative_tracking_error"])
    
    # Check for alerts
    alerts = []
    
    # Check mean deviation
    mean_deviation = abs(tracking_error.get("mean_deviation", 0.0))
    max_divergence = abs(tracking_error.get("max_divergence", 0.0))
    
    # Calculate deviation as percentage (assuming mean_deviation is absolute)
    # We need to normalize by theoretical equity to get percentage
    theoretical_equity = 10000.0  # Default, should be passed if available
    deviation_pct = (mean_deviation / theoretical_equity) * 100.0 if theoretical_equity > 0 else 0.0
    
    if deviation_pct > threshold_pct * 100:
        TRACKING_ERROR_ALERT_COUNT.labels(
            symbol=symbol, campaign_id=campaign_id, threshold=f"{threshold_pct*100:.0f}%"
        ).inc()
        
        alerts.append(
            {
                "type": "tracking_error_deviation",
                "symbol": symbol,
                "campaign_id": campaign_id,
                "metric": "mean_deviation",
                "value": mean_deviation,
                "deviation_pct": deviation_pct,
                "threshold_pct": threshold_pct * 100,
                "message": f"Tracking error deviation {deviation_pct:.2f}% exceeds threshold {threshold_pct*100:.0f}%",
            }
        )
    
    # Check correlation
    correlation = tracking_error.get("correlation", 1.0)
    if correlation < 0.90:  # Low correlation alert
        alerts.append(
            {
                "type": "tracking_error_low_correlation",
                "symbol": symbol,
                "campaign_id": campaign_id,
                "metric": "correlation",
                "value": correlation,
                "threshold": 0.90,
                "message": f"Tracking error correlation {correlation:.4f} is below threshold 0.90",
            }
        )
    
    return alerts



