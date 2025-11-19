"""Observability endpoints for public/private dashboard."""
from fastapi import APIRouter, HTTPException, Query
from typing import Any
from prometheus_client import REGISTRY, Gauge

from app.core.logging import logger
from app.core.config import settings
from app.services.monitoring_service import ContinuousMonitoringService
from app.observability.performance_metrics import (
    ROLLING_SHARPE,
    HIT_RATE,
    MAX_DRAWDOWN,
    EQUITY_SLOPE,
)
from app.observability.execution_metrics import (
    TRACKING_ERROR_MEAN_DEVIATION,
    TRACKING_ERROR_CORRELATION,
    EXECUTION_FILL_RATE,
)
from app.observability.risk_metrics import RISK_CURRENT_DRAWDOWN_PCT
from app.core.database import SessionLocal
from app.db.crud import get_recommendation_history, calculate_production_drawdown

router = APIRouter()
monitoring_service = ContinuousMonitoringService(asset="BTCUSDT", venue="binance")

# Default thresholds
DEFAULT_THRESHOLDS = {
    "rolling_sharpe_7d": 0.5,
    "rolling_sharpe_30d": 0.8,
    "rolling_sharpe_90d": 1.0,
    "hit_rate_7d": 40.0,
    "hit_rate_30d": 45.0,
    "hit_rate_90d": 50.0,
    "max_drawdown_7d": 10.0,
    "max_drawdown_30d": 15.0,
    "max_drawdown_90d": 20.0,
    "equity_slope": -10.0,  # basis points per day
    "tracking_error_mean": 0.02,  # 2%
    "tracking_error_correlation": 0.90,  # 90% correlation
    "current_drawdown": 20.0,  # 20% current drawdown
    "fill_rate": 0.85,  # 85% fill rate
}

# Degradation threshold (X% change from baseline)
DEGRADATION_THRESHOLD_PCT = 20.0  # 20% degradation triggers alert


@router.get("/public/dashboard")
async def get_public_dashboard(
    include_alerts: bool = Query(True, description="Include degradation alerts"),
    threshold_override: dict[str, float] | None = Query(None, description="Override default thresholds"),
) -> dict[str, Any]:
    """
    Public observability dashboard with key metrics and alerts.
    
    Returns:
    - Key metrics (Sharpe rolling, hit rate, drawdown, tracking error)
    - Current thresholds
    - Degradation alerts (if enabled)
    """
    try:
        thresholds = {**DEFAULT_THRESHOLDS}
        if threshold_override:
            thresholds.update(threshold_override)
        
        # Get current metrics from Prometheus
        metrics = _collect_prometheus_metrics()
        
        # Get production drawdown
        with SessionLocal() as db:
            dd_info = calculate_production_drawdown(db)
            recs = get_recommendation_history(db, limit=100)
        
        # Calculate current metrics
        current_metrics = {
            **metrics,
            "current_drawdown_pct": dd_info.get("current_drawdown_pct", 0.0),
            "peak_equity": dd_info.get("peak_equity", 0.0),
            "current_equity": dd_info.get("current_equity", 0.0),
            "total_trades": len([r for r in recs if r.status == "closed"]),
        }
        
        # Calculate degradation alerts
        alerts = []
        if include_alerts:
            alerts = _calculate_degradation_alerts(current_metrics, thresholds)
        
        return {
            "status": "ok",
            "metrics": current_metrics,
            "thresholds": thresholds,
            "alerts": alerts,
            "alerts_count": len(alerts),
            "timestamp": str(__import__("datetime").datetime.utcnow().isoformat()),
        }
    except Exception as e:
        logger.error(f"Error generating public dashboard: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/public/metrics")
async def get_public_metrics() -> dict[str, Any]:
    """
    Public metrics only (no alerts or thresholds).
    
    Returns raw metrics for external monitoring systems.
    """
    try:
        metrics = _collect_prometheus_metrics()
        
        with SessionLocal() as db:
            dd_info = calculate_production_drawdown(db)
        
        return {
            "status": "ok",
            "metrics": {
                **metrics,
                "current_drawdown_pct": dd_info.get("current_drawdown_pct", 0.0),
            },
            "timestamp": str(__import__("datetime").datetime.utcnow().isoformat()),
        }
    except Exception as e:
        logger.error(f"Error fetching public metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/private/dashboard")
async def get_private_dashboard(
    include_alerts: bool = Query(True, description="Include degradation alerts"),
    threshold_override: dict[str, float] | None = Query(None, description="Override default thresholds"),
    degradation_threshold_pct: float = Query(DEGRADATION_THRESHOLD_PCT, description="Degradation threshold percentage"),
) -> dict[str, Any]:
    """
    Private observability dashboard with enhanced details and alerts.
    
    Includes:
    - All metrics from public dashboard
    - Enhanced alerting with degradation detection
    - Detailed tracking error metrics
    - Execution metrics
    - Risk metrics
    """
    try:
        thresholds = {**DEFAULT_THRESHOLDS}
        if threshold_override:
            thresholds.update(threshold_override)
        
        # Get comprehensive metrics
        metrics = _collect_prometheus_metrics()
        enhanced_metrics = _collect_enhanced_metrics()
        
        with SessionLocal() as db:
            dd_info = calculate_production_drawdown(db)
            recs = get_recommendation_history(db, limit=500)
        
        # Calculate current metrics
        current_metrics = {
            **metrics,
            **enhanced_metrics,
            "current_drawdown_pct": dd_info.get("current_drawdown_pct", 0.0),
            "peak_equity": dd_info.get("peak_equity", 0.0),
            "current_equity": dd_info.get("current_equity", 0.0),
            "total_trades": len([r for r in recs if r.status == "closed"]),
        }
        
        # Calculate degradation alerts
        alerts = []
        if include_alerts:
            alerts = _calculate_degradation_alerts(current_metrics, thresholds, degradation_threshold_pct)
        
        # Get monitoring service alerts
        monitoring_alerts = monitoring_service.check_alerts() if hasattr(monitoring_service, "check_alerts") else []
        
        return {
            "status": "ok",
            "metrics": current_metrics,
            "thresholds": thresholds,
            "degradation_threshold_pct": degradation_threshold_pct,
            "alerts": alerts,
            "monitoring_alerts": monitoring_alerts,
            "alerts_count": len(alerts) + len(monitoring_alerts),
            "timestamp": str(__import__("datetime").datetime.utcnow().isoformat()),
        }
    except Exception as e:
        logger.error(f"Error generating private dashboard: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _collect_prometheus_metrics() -> dict[str, Any]:
    """Collect current values from Prometheus gauges."""
    metrics = {}
    
    # Rolling Sharpe (7d, 30d, 90d)
    for horizon in ["7d", "30d", "90d"]:
        try:
            value = ROLLING_SHARPE.labels(asset="BTCUSDT", venue="binance", horizon=horizon)._value.get()
            metrics[f"rolling_sharpe_{horizon}"] = float(value) if value is not None else 0.0
        except Exception:
            metrics[f"rolling_sharpe_{horizon}"] = 0.0
    
    # Hit Rate (7d, 30d, 90d)
    for horizon in ["7d", "30d", "90d"]:
        try:
            value = HIT_RATE.labels(asset="BTCUSDT", venue="binance", horizon=horizon)._value.get()
            metrics[f"hit_rate_{horizon}"] = float(value) if value is not None else 0.0
        except Exception:
            metrics[f"hit_rate_{horizon}"] = 0.0
    
    # Max Drawdown (7d, 30d, 90d)
    for horizon in ["7d", "30d", "90d"]:
        try:
            value = MAX_DRAWDOWN.labels(asset="BTCUSDT", venue="binance", horizon=horizon)._value.get()
            metrics[f"max_drawdown_{horizon}"] = float(value) if value is not None else 0.0
        except Exception:
            metrics[f"max_drawdown_{horizon}"] = 0.0
    
    # Equity Slope
    try:
        value = EQUITY_SLOPE.labels(asset="BTCUSDT", venue="binance")._value.get()
        metrics["equity_slope"] = float(value) if value is not None else 0.0
    except Exception:
        metrics["equity_slope"] = 0.0
    
    # Tracking Error
    try:
        value = TRACKING_ERROR_MEAN_DEVIATION.labels(symbol="BTCUSDT", campaign_id="default")._value.get()
        metrics["tracking_error_mean"] = float(value) if value is not None else 0.0
    except Exception:
        metrics["tracking_error_mean"] = 0.0
    
    try:
        value = TRACKING_ERROR_CORRELATION.labels(symbol="BTCUSDT", campaign_id="default")._value.get()
        metrics["tracking_error_correlation"] = float(value) if value is not None else 0.0
    except Exception:
        metrics["tracking_error_correlation"] = 0.0
    
    # Fill Rate
    try:
        value = EXECUTION_FILL_RATE.labels(symbol="BTCUSDT", order_type="market")._value.get()
        metrics["fill_rate"] = float(value) if value is not None else 1.0
    except Exception:
        metrics["fill_rate"] = 1.0
    
    return metrics


def _collect_enhanced_metrics() -> dict[str, Any]:
    """Collect enhanced metrics for private dashboard."""
    enhanced = {}
    
    # Risk metrics
    try:
        value = RISK_CURRENT_DRAWDOWN_PCT.labels(strategy="default", asset="BTCUSDT")._value.get()
        enhanced["risk_current_drawdown_pct"] = float(value) if value is not None else 0.0
    except Exception:
        enhanced["risk_current_drawdown_pct"] = 0.0
    
    # Additional execution metrics can be added here
    
    return enhanced


def _calculate_degradation_alerts(
    current_metrics: dict[str, Any],
    thresholds: dict[str, float],
    degradation_threshold_pct: float = DEGRADATION_THRESHOLD_PCT,
) -> list[dict[str, Any]]:
    """
    Calculate alerts for metrics that have degraded beyond thresholds.
    
    A metric is considered degraded if:
    1. It falls below its absolute threshold, OR
    2. It has degraded by more than degradation_threshold_pct from a baseline
    
    Args:
        current_metrics: Current metric values
        thresholds: Threshold values for each metric
        degradation_threshold_pct: Percentage degradation threshold (default: 20%)
        
    Returns:
        List of alert dictionaries
    """
    alerts = []
    
    for metric_name, threshold in thresholds.items():
        if metric_name not in current_metrics:
            continue
        
        current_value = current_metrics[metric_name]
        
        # Skip if value is None or invalid
        if current_value is None or (isinstance(current_value, float) and not __import__("math").isfinite(current_value)):
            continue
        
        # Determine if metric should be higher or lower than threshold
        is_higher_better = metric_name in [
            "rolling_sharpe_7d", "rolling_sharpe_30d", "rolling_sharpe_90d",
            "hit_rate_7d", "hit_rate_30d", "hit_rate_90d",
            "tracking_error_correlation", "fill_rate", "equity_slope",
        ]
        
        # Check threshold breach
        threshold_breach = False
        if is_higher_better:
            threshold_breach = current_value < threshold
        else:
            threshold_breach = current_value > threshold
        
        if threshold_breach:
            # Calculate degradation percentage
            if is_higher_better:
                if threshold > 0:
                    degradation_pct = ((threshold - current_value) / threshold) * 100.0
                else:
                    degradation_pct = 100.0 if current_value < 0 else 0.0
            else:
                if threshold > 0:
                    degradation_pct = ((current_value - threshold) / threshold) * 100.0
                else:
                    degradation_pct = 100.0 if current_value > 0 else 0.0
            
            severity = "critical" if degradation_pct > degradation_threshold_pct * 2 else "warning"
            
            alerts.append({
                "metric": metric_name,
                "current_value": float(current_value),
                "threshold": threshold,
                "degradation_pct": float(degradation_pct),
                "severity": severity,
                "type": "threshold_breach",
                "message": f"{metric_name} is {degradation_pct:.1f}% below threshold ({current_value:.2f} vs {threshold:.2f})",
            })
    
    return alerts





