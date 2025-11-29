"""Performance endpoints."""
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Response

from app.backtesting.guardrails import GuardrailChecker, GuardrailConfig
from app.models.performance import (
    PerformanceMetrics,
    PerformancePeriod,
    PerformanceSummaryResponse,
    RiskProfile,
    RollingMetrics,
)
from app.services.monitoring_service import ContinuousMonitoringService
from app.services.performance_service import get_performance_service
from app.services.kpis_reporting_service import KPIsReportingService
from app.core.logging import logger

router = APIRouter()
performance_service = get_performance_service()
monitoring_service = ContinuousMonitoringService(asset="BTCUSDT", venue="binance")
kpis_service = KPIsReportingService()


def _create_demo_metrics() -> PerformanceMetrics:
    """Create zero/demo metrics for degraded mode when cache is empty."""
    return PerformanceMetrics(
        cagr=0.0,
        sharpe=0.0,
        sortino=0.0,
        max_drawdown=0.0,
        win_rate=0.0,
        profit_factor=0.0,
        expectancy=0.0,
        calmar=0.0,
        total_return=0.0,
        total_trades=0,
        winning_trades=0,
        losing_trades=0,
        rolling_monthly=None,
        rolling_quarterly=None,
        risk_profile=None,
        tracking_error_rmse=None,
        tracking_error_max=None,
        orderbook_fallback_events=None,
    )


async def _background_backfill_summary(*, allow_stale_inputs: bool = False) -> None:
    """
    Background task to refresh performance summary cache.
    
    This runs asynchronously after the HTTP response is sent, ensuring
    UI requests never block on full backtest execution.
    """
    try:
        service = get_performance_service()
        summary = await service._run_backtest_and_cache(allow_stale_inputs=allow_stale_inputs)
        if summary:
            logger.info("Background backfill completed and cached new summary")
        else:
            logger.warning("Background backfill completed but no summary was generated")
    except Exception as exc:
        logger.exception(
            "Background backfill failed",
            extra={"error": str(exc), "error_type": type(exc).__name__},
        )


@router.post("/summary/calculate", response_model=PerformanceSummaryResponse)
async def calculate_performance_summary(
    allow_stale_inputs: bool = Query(False, description="Allow stale data inputs for calculation"),
):
    """
    Force calculation of performance metrics (run backtest in foreground).
    
    This endpoint triggers immediate backtest execution and caching,
    intended for administrative use or warmup scenarios.
    
    Returns:
        Performance summary with real metrics (blocks until calculation completes)
    
    Raises:
        HTTPException 503: If data is stale or has gaps (unless allow_stale_inputs=True)
        HTTPException 500: If calculation fails
    """
    try:
        logger.info("Forcing performance summary calculation (admin endpoint)")
        
        # Run backtest in foreground
        backfill_result = await performance_service._run_backtest_and_cache(
            allow_stale_inputs=allow_stale_inputs
        )
        
        if not backfill_result:
            raise HTTPException(
                status_code=500,
                detail={
                    "status": "calculation_failed",
                    "message": "Performance calculation completed but no result was generated. Check logs for details.",
                },
            )
        
        # Get the newly cached summary
        result = await performance_service.get_summary(
            allow_stale_inputs=allow_stale_inputs,
            trigger_backfill=False
        )
        
        # Process result similar to GET /summary
        metrics_dict = result.get("metrics", {})
        has_metrics = bool(metrics_dict and len(metrics_dict) > 0)
        
        if not has_metrics:
            raise HTTPException(
                status_code=500,
                detail={
                    "status": "calculation_failed",
                    "message": "Performance calculation completed but no metrics were generated.",
                },
            )
        
        # Build successful response (reuse logic from GET endpoint)
        # This will be processed by the normal response building logic below
        # For now, return the result directly
        if result.get("status") == "error":
            raise HTTPException(
                status_code=503,
                detail={
                    "status": result.get("error_type", "error"),
                    "message": result.get("message", "Performance calculation failed"),
                },
            )
        
        # Return the calculated summary
        return PerformanceSummaryResponse.model_validate(result)
        
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error forcing performance summary calculation")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/summary", response_model=PerformanceSummaryResponse)
async def get_performance_summary(
    background_tasks: BackgroundTasks,
    allow_stale_inputs: bool = Query(False, description="Allow stale data inputs to return degraded results with fallback summary"),
    warmup: bool = Query(False, description="Force foreground calculation on cache miss (warmup mode)"),
):
    """
    Get backtesting performance summary with metrics and disclaimer.

    Returns comprehensive metrics including CAGR, Sharpe, Sortino, Max Drawdown,
    Win Rate, Profit Factor, Expectancy, Calmar, and rolling KPIs (monthly/quarterly).
    
    When allow_stale_inputs=True:
    - Returns cached data immediately (cache-first fast path)
    - Enqueues background backfill to refresh cache asynchronously
    - Never blocks UI requests on full backtest execution
    - Response includes metadata: served_from_cache, generated_at
    
    When warmup=True:
    - If cache miss detected, runs backtest in foreground (blocking)
    - Ensures first request gets real metrics instead of demo
    - Use this for initial setup or when forcing recalculation
    """
    try:
        from app.core.config import settings
        
        # In dev mode, only allow stale inputs if we have valid cache
        # This prevents serving demo metrics when cache is empty
        if allow_stale_inputs and settings.DEV_FAKE_DATA:
            # Check if we have valid cache before allowing stale inputs
            cached_summary = performance_service._get_db_cached_success_summary(max_age_seconds=86400)
            if not cached_summary:
                logger.info(
                    "allow_stale_inputs requested in dev mode but no valid cache exists - forcing warmup instead",
                )
                # Force warmup mode to populate cache instead of returning demo metrics
                warmup = True
                allow_stale_inputs = False
        
        result = await performance_service.get_summary(allow_stale_inputs=allow_stale_inputs, trigger_backfill=True)
        
        # Check for cache miss with empty metrics
        metadata = result.get("metadata", {})
        cache_miss = metadata.get("cache_miss", False)
        metrics_dict = result.get("metrics", {})
        has_metrics = bool(metrics_dict and len(metrics_dict) > 0)
        
        # If cache miss and no metrics, handle based on warmup mode
        if cache_miss and not has_metrics:
            if warmup:
                # WARMUP MODE: Run backtest in foreground to get real metrics
                logger.info(
                    "Cache miss detected in warmup mode - running backtest in foreground",
                    extra={"cache_miss": cache_miss, "has_metrics": has_metrics, "warmup": warmup},
                )
                try:
                    # Run backtest synchronously
                    backfill_result = await performance_service._run_backtest_and_cache(
                        allow_stale_inputs=allow_stale_inputs
                    )
                    if backfill_result:
                        # Get the newly cached summary
                        result = await performance_service.get_summary(
                            allow_stale_inputs=allow_stale_inputs, 
                            trigger_backfill=False
                        )
                        # Re-check if we now have metrics
                        metrics_dict = result.get("metrics", {})
                        has_metrics = bool(metrics_dict and len(metrics_dict) > 0)
                        if has_metrics:
                            logger.info("Warmup backtest completed successfully - returning real metrics")
                            # Continue to normal response processing below
                        else:
                            logger.warning("Warmup backtest completed but no metrics in result")
                            # Fall through to degraded response
                    else:
                        logger.warning("Warmup backtest failed - returning degraded response")
                        # Fall through to degraded response
                except Exception as exc:
                    logger.exception(
                        "Warmup backtest failed with exception - returning degraded response",
                        extra={"error": str(exc), "error_type": type(exc).__name__},
                    )
                    # Fall through to degraded response
            
            # If still no metrics after warmup attempt, or warmup=False, return degraded
            if not has_metrics:
                logger.info(
                    "Cache miss detected with no metrics - returning degraded response with demo metrics",
                    extra={"cache_miss": cache_miss, "has_metrics": has_metrics, "warmup": warmup},
                )
                # Trigger background backfill immediately (non-blocking)
                if not warmup:  # Don't trigger background if we just tried warmup
                    background_tasks.add_task(
                        _background_backfill_summary,
                        allow_stale_inputs=allow_stale_inputs
                    )
                    logger.info("Enqueued background backfill for performance summary (cache miss)")
                
                # Return degraded response with demo metrics
                demo_metrics = _create_demo_metrics()
                demo_cause = "cache_miss"
                if warmup:
                    demo_cause = "warmup_failed"
                elif cache_miss:
                    demo_cause = "cache_miss"
                
                response = PerformanceSummaryResponse(
                    status="degraded",
                    message="No backtest cache available; showing demo metrics. Real metrics will be available after background backfill completes." + 
                           (" Use warmup=true to calculate immediately." if not warmup else ""),
                    metrics=demo_metrics,
                    period=None,
                    report_path=None,
                    tracking_error_rmse=None,
                    tracking_error_max=None,
                    orderbook_fallback_events=None,
                    has_realistic_data=False,
                    tracking_error_metrics=None,
                    tracking_error_series=None,
                    tracking_error_cumulative=None,
                    chart_banners=[f"No backtest data available - showing demo metrics (cause: {demo_cause})"],
                )
                response_dict = response.model_dump()
                # Add metadata about demo metrics cause and cache status
                response_dict["demo_metrics_cause"] = demo_cause
                response_dict["demo_metrics"] = True
                response_dict["cache_miss"] = True
                response_dict["metrics_status"] = "CACHE_MISS"
                response_dict["degraded_reason"] = f"cache_miss_{demo_cause}"
                return response_dict
        
        # Server-side guardrail: When allow_stale_inputs=True, enqueue background backfill if needed
        # This ensures cache stays fresh without blocking the response
        if allow_stale_inputs:
            # Check if we should trigger a background backfill
            # Only trigger if cache is missing or very old (> 1 hour for UI requests)
            cache_age = result.get("cache_age_seconds") or metadata.get("cache_age_seconds")
            served_from_cache = metadata.get("served_from_cache", False)
            
            # Enqueue background backfill if:
            # 1. Cache miss (no data available) - already handled above
            # 2. Cache is old (> 1 hour)
            # This runs after response is sent, never blocking the UI
            if not served_from_cache or (cache_age is not None and cache_age > 3600):
                background_tasks.add_task(
                    _background_backfill_summary,
                    allow_stale_inputs=allow_stale_inputs
                )
                logger.info(
                    "Enqueued background backfill for performance summary",
                    extra={
                        "cache_miss": cache_miss,
                        "served_from_cache": served_from_cache,
                        "cache_age_seconds": cache_age,
                    },
                )

        if result.get("status") == "error":
            error_type = result.get("error_type")
            if error_type == "CONFIG":
                raise HTTPException(
                    status_code=result.get("http_status", 400),
                    detail={
                        "message": result.get("message", "Strategy configuration error"),
                        "error_type": error_type,
                        "details": result.get("details", {}),
                    },
                )
            
            # For DATA_STALE errors with fallback_summary, include optional fields
            fallback_summary = result.get("fallback_summary")
            if error_type == "DATA_STALE" and fallback_summary:
                # Extract metrics from fallback_summary if available
                fallback_metrics = fallback_summary.get("metrics", {})
                fallback_period = fallback_summary.get("period")
                
                # Build response with fallback data for degraded mode
                response_dict = {
                    "status": "error",
                    "message": result.get("message", "Unknown error"),
                    "metrics": None,
                    "period": None,
                    "report_path": None,
                    # Include optional fields from fallback_summary for frontend compatibility
                    "equity_theoretical": fallback_summary.get("equity_theoretical", []),
                    "equity_realistic": fallback_summary.get("equity_realistic", []),
                    "equity_curve": fallback_summary.get("equity_curve", []),
                    "tracking_error_metrics": fallback_summary.get("tracking_error_metrics"),
                    "tracking_error": fallback_summary.get("tracking_error"),
                }
                
                # Try to build period if available
                if fallback_period:
                    try:
                        response_dict["period"] = PerformancePeriod(
                            start=fallback_period.get("start", ""),
                            end=fallback_period.get("end", ""),
                        )
                    except Exception:
                        pass
                
                # Try to build metrics if available (may fail if incomplete)
                if fallback_metrics:
                    try:
                        rolling_monthly = fallback_metrics.get("rolling_monthly")
                        rolling_quarterly = fallback_metrics.get("rolling_quarterly")
                        risk_profile_dict = fallback_metrics.get("risk_profile")
                        risk_profile = RiskProfile(**risk_profile_dict) if risk_profile_dict else None
                        
                        response_dict["metrics"] = PerformanceMetrics(
                            cagr=fallback_metrics.get("cagr", 0.0),
                            sharpe=fallback_metrics.get("sharpe", 0.0),
                            sortino=fallback_metrics.get("sortino", 0.0),
                            max_drawdown=fallback_metrics.get("max_drawdown", 0.0),
                            win_rate=fallback_metrics.get("win_rate", 0.0),
                            profit_factor=fallback_metrics.get("profit_factor", 0.0),
                            expectancy=fallback_metrics.get("expectancy", 0.0),
                            calmar=fallback_metrics.get("calmar", 0.0),
                            total_return=fallback_metrics.get("total_return", 0.0),
                            total_trades=fallback_metrics.get("total_trades", 0),
                            winning_trades=fallback_metrics.get("winning_trades", 0),
                            losing_trades=fallback_metrics.get("losing_trades", 0),
                            rolling_monthly=RollingMetrics(**rolling_monthly) if rolling_monthly else None,
                            rolling_quarterly=RollingMetrics(**rolling_quarterly) if rolling_quarterly else None,
                            risk_profile=risk_profile,
                            tracking_error_rmse=fallback_metrics.get("tracking_error_rmse"),
                            tracking_error_max=fallback_metrics.get("tracking_error_max"),
                            orderbook_fallback_events=fallback_metrics.get("orderbook_fallback_events"),
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to build PerformanceMetrics from fallback_summary",
                            extra={"error": str(e), "fallback_metrics_keys": list(fallback_metrics.keys())},
                        )
                
                # Build response model and return as dict with additional fields
                response = PerformanceSummaryResponse(**response_dict)
                response_dict = response.model_dump()
                # Preserve equity fields that aren't in the model
                response_dict["equity_theoretical"] = fallback_summary.get("equity_theoretical", [])
                response_dict["equity_realistic"] = fallback_summary.get("equity_realistic", [])
                response_dict["equity_curve"] = fallback_summary.get("equity_curve", [])
                return response_dict
            
            # For other error types without fallback, return degraded response with demo metrics
            # This ensures the frontend can render something instead of showing an error state
            logger.warning(
                "Error status without fallback_summary - returning degraded response with demo metrics",
                extra={
                    "error_type": error_type,
                    "message": result.get("message"),
                },
            )
            demo_metrics = _create_demo_metrics()
            response = PerformanceSummaryResponse(
                status="degraded",
                message=f"{result.get('message', 'Unknown error')}. Showing demo metrics until backtest completes.",
                metrics=demo_metrics,
                period=None,
                report_path=None,
                chart_banners=[f"Error: {result.get('message', 'Unknown error')} - showing demo metrics (cause: error_no_fallback)"],
            )
            response_dict = response.model_dump()
            response_dict["demo_metrics_cause"] = "error_no_fallback"
            response_dict["demo_metrics"] = True
            return response_dict

        metrics_dict = result.get("metrics", {})
        
        # Initialize demo metrics flags
        demo_metrics_used = False
        demo_metrics_cause = None
        
        # If metrics dict is empty, use demo metrics instead of failing
        if not metrics_dict or len(metrics_dict) == 0:
            logger.warning("Empty metrics dict in result - using demo metrics for degraded response")
            metrics = _create_demo_metrics()
            # Mark as demo metrics with cause
            demo_metrics_used = True
            demo_metrics_cause = "empty_metrics_dict"
        else:
            rolling_monthly = metrics_dict.get("rolling_monthly")
            rolling_quarterly = metrics_dict.get("rolling_quarterly")

            risk_profile_dict = metrics_dict.get("risk_profile")
            risk_profile = RiskProfile(**risk_profile_dict) if risk_profile_dict else None

            metrics = PerformanceMetrics(
                cagr=metrics_dict.get("cagr", 0.0),
                sharpe=metrics_dict.get("sharpe", 0.0),
                sortino=metrics_dict.get("sortino", 0.0),
                max_drawdown=metrics_dict.get("max_drawdown", 0.0),
                win_rate=metrics_dict.get("win_rate", 0.0),
                profit_factor=metrics_dict.get("profit_factor", 0.0),
                expectancy=metrics_dict.get("expectancy", 0.0),
                calmar=metrics_dict.get("calmar", 0.0),
                total_return=metrics_dict.get("total_return", 0.0),
                total_trades=metrics_dict.get("total_trades", 0),
                winning_trades=metrics_dict.get("winning_trades", 0),
                losing_trades=metrics_dict.get("losing_trades", 0),
                rolling_monthly=RollingMetrics(**rolling_monthly) if rolling_monthly else None,
                rolling_quarterly=RollingMetrics(**rolling_quarterly) if rolling_quarterly else None,
                risk_profile=risk_profile,
                tracking_error_rmse=metrics_dict.get("tracking_error_rmse"),
                tracking_error_max=metrics_dict.get("tracking_error_max"),
                orderbook_fallback_events=metrics_dict.get("orderbook_fallback_events"),
            )
        
        # Extract tracking error data from backtest result
        tracking_error = result.get("tracking_error")
        execution_stats = result.get("execution_stats", {})
        has_realistic_data = bool(result.get("equity_realistic") and len(result.get("equity_realistic", [])) > 0)
        
        tracking_error_rmse = None
        tracking_error_max = None
        if tracking_error and isinstance(tracking_error, dict):
            tracking_error_rmse = tracking_error.get("rmse")
            tracking_error_max_bps = tracking_error.get("max_divergence_bps")
            if tracking_error_max_bps is not None:
                tracking_error_max = tracking_error_max_bps
        
        orderbook_fallback_events = execution_stats.get("rejected_orders", 0)

        period_dict = result.get("period", {})
        period = PerformancePeriod(
            start=period_dict.get("start", ""),
            end=period_dict.get("end", ""),
        ) if period_dict else None

        # Deployment guardrails: handle non-PASS statuses gracefully
        oos_days = result.get("oos_days")
        # ROOT CAUSE FIX BE-METRICS-01: When metrics_status is missing, distinguish between:
        # - NO_TRADES: Minimal metrics only (just total_trades=0, winning_trades=0, losing_trades=0)
        # - FALLBACK_NO_TRADES: Fallback/synthetic metrics exist (has CAGR, Sharpe, etc. even if trade_count=0)
        metrics_status = result.get("metrics_status")
        if not metrics_status or metrics_status == "UNKNOWN":
            # Determine fallback status based on trade count and metrics content
            metrics_dict = result.get("metrics", {})
            trade_count = metrics_dict.get("total_trades", 0) or result.get("trade_count", 0)
            if trade_count == 0:
                # Check if metrics contain fallback/synthetic values vs minimal structure only
                has_fallback_metrics = bool(
                    metrics_dict.get("cagr") is not None
                    or metrics_dict.get("sharpe_ratio") is not None
                    or metrics_dict.get("max_drawdown") is not None
                    or len(metrics_dict) > 3  # More than just total_trades, winning_trades, losing_trades
                )
                if has_fallback_metrics:
                    # Fallback metrics were generated despite zero trades
                    metrics_status = "FALLBACK_NO_TRADES"
                else:
                    # Minimal metrics only - no fallback/synthetic values
                    metrics_status = "NO_TRADES"
            else:
                # For non-zero trades but missing status, use DEV_FALLBACK if in dev mode
                from app.core.config import settings
                dev_mode = settings.is_dev_mode()
                if dev_mode:
                    metrics_status = "DEV_FALLBACK"
                else:
                    metrics_status = "FALLBACK_NO_TRADES"  # Conservative fallback
        
        if oos_days is not None and oos_days < 120:
            logger.warning(
                "Summary degraded: insufficient OOS period",
                extra={"oos_days": oos_days, "required": 120}
            )
            # Return degraded response with available metrics instead of error
            response = PerformanceSummaryResponse(
                status="degraded",
                message=f"Metrics available but not validated: OOS period ({oos_days} days) is less than required minimum (120 days). Metrics shown for informational purposes only.",
                metrics=metrics,
                period=period,
                report_path=result.get("report_path"),
                tracking_error_rmse=tracking_error_rmse,
                tracking_error_max=tracking_error_max,
                orderbook_fallback_events=orderbook_fallback_events,
                has_realistic_data=has_realistic_data,
                tracking_error_metrics=result.get("tracking_error_metrics"),
                tracking_error_series=result.get("tracking_error_series"),
                tracking_error_cumulative=result.get("tracking_error_cumulative"),
                chart_banners=result.get("chart_banners", []) + [f"OOS period ({oos_days} days) below minimum (120 days)"],
            )
            response_dict = response.model_dump()
            response_dict["equity_theoretical"] = result.get("equity_theoretical", [])
            response_dict["equity_realistic"] = result.get("equity_realistic", [])
            response_dict["equity_curve"] = result.get("equity_curve", [])
            response_dict["equity_curve_theoretical"] = result.get("equity_curve_theoretical", [])
            response_dict["equity_curve_realistic"] = result.get("equity_curve_realistic", [])
            return response_dict
        
        if metrics_status != "PASS":
            # For non-PASS statuses, return degraded response with available metrics
            # This allows dashboards to show data with appropriate warnings instead of error banners
            logger.info(
                "Summary returned in degraded mode: metrics status not PASS",
                extra={"metrics_status": metrics_status, "has_metrics": metrics is not None}
            )
            
            # Extract degraded reason from metadata if available
            metadata = result.get("metadata", {})
            degraded_reason = metadata.get("degraded_reason") or result.get("metrics", {}).get("degraded_reason")
            trade_count = metadata.get("trade_count") or result.get("metrics", {}).get("total_trades", 0)
            
            # Extract no-trade diagnostics from metadata if available
            metadata = result.get("metadata", {})
            no_trade_diagnostics = metadata.get("no_trade_diagnostics")
            no_trade_root_cause = metadata.get("no_trade_root_cause")
            no_trade_reason = metadata.get("no_trade_reason")
            
            # Build human-readable status messages for explicit statuses
            status_messages = {
                "FALLBACK_NO_TRADES": no_trade_reason if no_trade_reason else f"No trades executed during backtest period (trade_count: {trade_count}). Conservative fallback metrics provided.",
                "FAIL": "Metrics validation failed. Data shown for informational purposes only.",
                "DEV_FALLBACK": f"Development mode: Fallback metrics generated due to insufficient trades ({trade_count} < 50). Data shown for informational purposes only.",
                "NO_TRADES": no_trade_reason if no_trade_reason else f"No trades executed during backtest period (trade_count: {trade_count}). Performance metrics unavailable.",
                "INSUFFICIENT_DATA": f"Fewer trades than minimum guardrail ({trade_count} < 50). Metrics informational only.",
            }
            
            # Use explicit message if available, otherwise build from reason
            if metrics_status in status_messages:
                status_message = status_messages[metrics_status]
            elif degraded_reason:
                # Build message from reason
                reason_messages = {
                    "no_trades_executed": no_trade_reason if no_trade_reason else f"No trades executed during backtest period (trade_count: {trade_count}). Fallback metrics generated.",
                    "no_trades_executed_no_signals_generated": "Strategy did not generate any signals during the backtest period. This may indicate strategy conditions were not met or strategy logic is flat.",
                    "no_trades_executed_no_enter_signals": "Strategy generated signals but none were 'enter' actions. Strategy may be in a hold/wait state.",
                    "no_trades_executed_enter_signals_zero_size": "Strategy generated enter signals but position sizer calculated zero size. This may indicate insufficient capital, risk limits, or invalid stop loss distances.",
                    "no_trades_executed_orders_rejected": "Strategy generated enter signals but orders were rejected by execution simulator (insufficient depth, price moved, etc.).",
                    "no_trades_executed_unknown": "Zero trades despite enter signals. Root cause unknown - check signal counts and execution logs.",
                    "insufficient_trades_dev_mode": f"Development mode: Insufficient trades ({trade_count} < 50). Fallback metrics generated.",
                    "insufficient_trades_guardrail_bypass": f"Development mode: Guardrail bypassed due to insufficient trades ({trade_count} < 50). Fallback metrics generated.",
                    "guardrail_validation_failed": "Guardrail validation failed. Metrics shown for informational purposes only.",
                }
                status_message = reason_messages.get(degraded_reason, f"Metrics status: {metrics_status}. {degraded_reason}")
            else:
                status_message = f"Metrics status is '{metrics_status}'. Data shown for informational purposes only."
            
            # Extract dev_bypass from metadata if available
            dev_bypass = metadata.get("dev_bypass")
            guardrail_bypass = metadata.get("guardrail_bypass")
            guardrail_bypass_reason = metadata.get("guardrail_bypass_reason")
            guardrail_bypass_details = metadata.get("guardrail_bypass_details")
            
            if not dev_bypass and metrics_status == "DEV_FALLBACK":
                # Try to extract from guardrail result if available
                dev_bypass = "min_trades"  # Default for DEV_FALLBACK
            
            # Surface guardrail bypass explicitly in API metadata
            if guardrail_bypass or metrics_status == "DEV_FALLBACK":
                if not guardrail_bypass:
                    guardrail_bypass = True
                    guardrail_bypass_reason = guardrail_bypass_reason or "insufficient_trades_dev_mode"
                    guardrail_bypass_details = guardrail_bypass_details or {
                        "trade_count": trade_count,
                        "min_required": 50,
                        "dev_mode": True,
                    }
            
            # Build chart banner with status info
            chart_banner = f"Metrics status: {metrics_status}"
            if degraded_reason:
                chart_banner += f" ({degraded_reason})"
            if metrics_status == "NO_TRADES" and no_trade_root_cause:
                chart_banner += f" - Root cause: {no_trade_root_cause}"
            chart_banner += " - data shown for informational purposes"
            
            response = PerformanceSummaryResponse(
                status="degraded",
                message=status_message,
                metrics=metrics,  # Include available metrics even if not validated
                period=period,
                report_path=result.get("report_path"),
                tracking_error_rmse=tracking_error_rmse,
                tracking_error_max=tracking_error_max,
                orderbook_fallback_events=orderbook_fallback_events,
                has_realistic_data=has_realistic_data,
                tracking_error_metrics=result.get("tracking_error_metrics"),
                tracking_error_series=result.get("tracking_error_series"),
                tracking_error_cumulative=result.get("tracking_error_cumulative"),
                chart_banners=result.get("chart_banners", []) + [chart_banner],
                metrics_status=metrics_status,
                dev_bypass=dev_bypass,
                fallback_reason=degraded_reason,
                trade_count=trade_count,
            )
            
            # Add guardrail bypass metadata to response dict
            response_dict = response.model_dump()
            if guardrail_bypass:
                response_dict["guardrail_bypass"] = guardrail_bypass
                response_dict["guardrail_bypass_reason"] = guardrail_bypass_reason
                response_dict["guardrail_bypass_details"] = guardrail_bypass_details
            if "response_dict" not in locals():
                response_dict = response.model_dump()
            response_dict["equity_theoretical"] = result.get("equity_theoretical", [])
            response_dict["equity_realistic"] = result.get("equity_realistic", [])
            response_dict["equity_curve"] = result.get("equity_curve", [])
            response_dict["equity_curve_theoretical"] = result.get("equity_curve_theoretical", [])
            response_dict["equity_curve_realistic"] = result.get("equity_curve_realistic", [])
            
            # Include no-trade diagnostics in response if available
            if metrics_status in ("NO_TRADES", "FALLBACK_NO_TRADES") and no_trade_diagnostics:
                response_dict["no_trade_diagnostics"] = no_trade_diagnostics
                response_dict["no_trade_root_cause"] = no_trade_root_cause
            
            # Include conservative TP probability and expected return if available
            conservative_tp_prob = metrics_dict.get("conservative_tp_probability")
            conservative_expected_return = metrics_dict.get("conservative_expected_return")
            if conservative_tp_prob is not None:
                response_dict["conservative_tp_probability"] = conservative_tp_prob
                response_dict["conservative_expected_return"] = conservative_expected_return
                response_dict["conservative_estimates_reason"] = metrics_dict.get("conservative_estimates_reason")
            
            return response_dict
        
        # Extract metrics_status and related fields from result
        metrics_status = result.get("metrics_status", "PASS")
        metadata = result.get("metadata", {})
        dev_bypass = metadata.get("dev_bypass")
        fallback_reason = metadata.get("degraded_reason") or result.get("metrics", {}).get("degraded_reason")
        trade_count = metrics.total_trades if metrics else None
        
        response = PerformanceSummaryResponse(
            status="success" if not demo_metrics_used else "degraded",
            metrics=metrics,
            period=period,
            report_path=result.get("report_path"),
            message=None if not demo_metrics_used else "Empty metrics dict - showing demo metrics",
            tracking_error_rmse=tracking_error_rmse,
            tracking_error_max=tracking_error_max,
            orderbook_fallback_events=orderbook_fallback_events,
            has_realistic_data=has_realistic_data,
            tracking_error_metrics=result.get("tracking_error_metrics"),
            tracking_error_series=result.get("tracking_error_series"),
            tracking_error_cumulative=result.get("tracking_error_cumulative"),
            chart_banners=result.get("chart_banners", []) + (["Empty metrics dict - showing demo metrics"] if demo_metrics_used else []),
            metrics_status=metrics_status if metrics_status != "PASS" or demo_metrics_used else None,  # Only include if not PASS
            dev_bypass=dev_bypass,
            fallback_reason=fallback_reason,
            trade_count=trade_count,
        )
        
        # Add equity data to response model (will be in response body but not in schema)
        response_dict = response.model_dump()
        response_dict["equity_theoretical"] = result.get("equity_theoretical", [])
        response_dict["equity_realistic"] = result.get("equity_realistic", [])
        response_dict["equity_curve"] = result.get("equity_curve", [])
        response_dict["equity_curve_theoretical"] = result.get("equity_curve_theoretical", [])
        response_dict["equity_curve_realistic"] = result.get("equity_curve_realistic", [])
        
        # Add demo metrics metadata if applicable
        if demo_metrics_used:
            response_dict["demo_metrics"] = True
            response_dict["demo_metrics_cause"] = demo_metrics_cause
        
        # Include signal_counts and rejected_orders_count when metrics_status ≠ PASS (for observability dashboard)
        if metrics_status and metrics_status != "PASS":
            no_trade_diagnostics = result.get("no_trade_diagnostics") or metadata.get("no_trade_diagnostics")
            if no_trade_diagnostics:
                response_dict["signal_counts"] = no_trade_diagnostics.get("signal_counts", {})
                response_dict["rejected_orders_count"] = no_trade_diagnostics.get("rejected_orders_count", 0)
                response_dict["no_trade_diagnostics"] = no_trade_diagnostics
                response_dict["no_trade_root_cause"] = no_trade_diagnostics.get("root_cause", "unknown")
        
        # Always expose cache_miss and degraded_reason in metadata for frontend
        if metadata.get("cache_miss"):
            response_dict["cache_miss"] = True
        if metadata.get("degraded_reason"):
            response_dict["degraded_reason"] = metadata.get("degraded_reason")
        if metadata.get("served_from_cache") is not None:
            response_dict["served_from_cache"] = metadata.get("served_from_cache")
        
        return response_dict
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/monitoring/health")
async def get_monitoring_health():
    """
    Get current performance monitoring health status with metrics and alerts.
    
    Returns current rolling metrics, regime probabilities, and any active alerts.
    """
    try:
        metrics = monitoring_service.get_current_metrics()
        alerts = monitoring_service.check_alerts()
        
        return {
            "status": "ok",
            "metrics": metrics,
            "alerts": alerts,
            "alerts_count": len(alerts),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/monitoring/metrics")
async def get_monitoring_metrics():
    """
    Get current Prometheus performance metrics (rolling Sharpe, hit rate, equity slope, regime).
    
    Returns all current metric values from Prometheus gauges.
    """
    try:
        metrics = monitoring_service.get_current_metrics()
        return {
            "status": "ok",
            "metrics": metrics,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/monthly")
async def get_monthly_performance():
    """
    Get detailed monthly performance with returns, streaks, and current drawdown.
    
    Returns:
    - Monthly returns table
    - Best/worst month
    - Current win/loss streak
    - Current drawdown
    """
    from app.services.performance_service import get_performance_service
    from app.core.database import SessionLocal
    from app.db.crud import get_recommendation_history, calculate_production_drawdown
    from datetime import datetime
    import pandas as pd

    perf_service = get_performance_service()
    
    # Get production trades from recommendations
    with SessionLocal() as db:
        recs = get_recommendation_history(db, limit=500)
        dd_info = calculate_production_drawdown(db)
    
    # Filter closed trades
    closed_trades = []
    for rec in recs:
        if rec.status == "closed" and rec.exit_price and rec.entry_optimal:
            exit_date = rec.closed_at or rec.created_at
            if rec.signal == "BUY":
                return_pct = ((rec.exit_price - rec.entry_optimal) / rec.entry_optimal) * 100
            elif rec.signal == "SELL":
                return_pct = ((rec.entry_optimal - rec.exit_price) / rec.entry_optimal) * 100
            else:
                return_pct = 0.0
            
            closed_trades.append({
                "date": exit_date,
                "return_pct": return_pct,
                "signal": rec.signal,
                "is_win": return_pct > 0,
            })
    
    if not closed_trades:
        return {
            "status": "no_data",
            "monthly_returns": [],
            "best_month": None,
            "worst_month": None,
            "current_streak": {"type": "none", "count": 0},
            "current_drawdown": dd_info.get("current_drawdown_pct", 0.0),
            "peak_equity": dd_info.get("peak_equity", 0.0),
            "current_equity": dd_info.get("current_equity", 0.0),
        }
    
    # Calculate monthly returns
    df_trades = pd.DataFrame(closed_trades)
    df_trades["date"] = pd.to_datetime(df_trades["date"])
    df_trades["year_month"] = df_trades["date"].dt.to_period("M")
    
    monthly_returns = []
    monthly_groups = df_trades.groupby("year_month")
    
    for period, group in monthly_groups:
        total_return = group["return_pct"].sum()
        trade_count = len(group)
        wins = group["is_win"].sum()
        losses = trade_count - wins
        win_rate = (wins / trade_count * 100) if trade_count > 0 else 0.0
        
        monthly_returns.append({
            "month": str(period),
            "year": period.year,
            "month_num": period.month,
            "return_pct": round(total_return, 2),
            "trade_count": trade_count,
            "wins": int(wins),
            "losses": int(losses),
            "win_rate": round(win_rate, 2),
        })
    
    # Sort by date (most recent first)
    monthly_returns.sort(key=lambda x: (x["year"], x["month_num"]), reverse=True)
    
    # Find best and worst month
    best_month = max(monthly_returns, key=lambda x: x["return_pct"]) if monthly_returns else None
    worst_month = min(monthly_returns, key=lambda x: x["return_pct"]) if monthly_returns else None
    
    # Calculate current streak (from most recent trades)
    sorted_trades = sorted(closed_trades, key=lambda x: x["date"], reverse=True)
    current_streak = {"type": "none", "count": 0}
    
    if sorted_trades:
        first_result = sorted_trades[0]["is_win"]
        streak_type = "win" if first_result else "loss"
        streak_count = 1
        
        for i in range(1, len(sorted_trades)):
            if sorted_trades[i]["is_win"] == first_result:
                streak_count += 1
            else:
                break
        
        current_streak = {"type": streak_type, "count": streak_count}
    
    # Get current drawdown
    current_dd_pct = dd_info.get("current_drawdown_pct", 0.0)
    peak_equity = dd_info.get("peak_equity", 0.0)
    current_equity = dd_info.get("current_equity", 0.0)
    
    return {
        "status": "ok",
        "monthly_returns": monthly_returns,
        "best_month": best_month,
        "worst_month": worst_month,
        "current_streak": current_streak,
        "current_drawdown": round(current_dd_pct, 2),
        "peak_equity": round(peak_equity, 2),
        "current_equity": round(current_equity, 2),
        "total_trades": len(closed_trades),
    }


@router.get("/monthly/export")
async def export_monthly_report(
    format: str = Query("csv", regex="^(csv|parquet)$"),
) -> Response:
    """
    Export monthly performance report with hashes for verification.
    
    Returns CSV or Parquet file with monthly returns, streaks, and drawdown data.
    Includes metadata: commit_hash, dataset_hash, params_hash.
    """
    from fastapi.responses import Response
    from app.utils.hashing import calculate_file_md5, calculate_file_sha256, get_git_commit_hash
    from app.utils.dataset_metadata import get_dataset_version_hash, get_params_digest
    from app.db.models import ExportAuditORM
    from app.core.database import SessionLocal
    from app.db.crud import get_recommendation_history, calculate_production_drawdown
    import io
    import pandas as pd
    
    # Get monthly performance data (reuse logic from get_monthly_performance)
    with SessionLocal() as db:
        recs = get_recommendation_history(db, limit=500)
        dd_info = calculate_production_drawdown(db)
    
    # Filter closed trades
    closed_trades = []
    for rec in recs:
        if rec.status == "closed" and rec.exit_price and rec.entry_optimal:
            exit_date = rec.closed_at or rec.created_at
            if rec.signal == "BUY":
                return_pct = ((rec.exit_price - rec.entry_optimal) / rec.entry_optimal) * 100
            elif rec.signal == "SELL":
                return_pct = ((rec.entry_optimal - rec.exit_price) / rec.entry_optimal) * 100
            else:
                return_pct = 0.0
            
            closed_trades.append({
                "date": exit_date,
                "return_pct": return_pct,
                "signal": rec.signal,
                "is_win": return_pct > 0,
            })
    
    if not closed_trades:
        raise HTTPException(status_code=404, detail="No monthly data available for export")
    
    # Calculate monthly returns
    df_trades = pd.DataFrame(closed_trades)
    df_trades["date"] = pd.to_datetime(df_trades["date"])
    df_trades["year_month"] = df_trades["date"].dt.to_period("M")
    
    export_records = []
    monthly_groups = df_trades.groupby("year_month")
    
    for period, group in monthly_groups:
        total_return = group["return_pct"].sum()
        trade_count = len(group)
        wins = group["is_win"].sum()
        losses = trade_count - wins
        win_rate = (wins / trade_count * 100) if trade_count > 0 else 0.0
        
        export_records.append({
            "month": str(period),
            "year": period.year,
            "month_num": period.month,
            "return_pct": round(total_return, 2),
            "trade_count": trade_count,
            "wins": int(wins),
            "losses": int(losses),
            "win_rate": round(win_rate, 2),
        })
    
    export_records.sort(key=lambda x: (x["year"], x["month_num"]), reverse=True)
    best_month = max(export_records, key=lambda x: x["return_pct"]) if export_records else None
    worst_month = min(export_records, key=lambda x: x["return_pct"]) if export_records else None
    
    sorted_trades = sorted(closed_trades, key=lambda x: x["date"], reverse=True)
    current_streak = {"type": "none", "count": 0}
    
    if sorted_trades:
        first_result = sorted_trades[0]["is_win"]
        streak_type = "win" if first_result else "loss"
        streak_count = 1
        
        for i in range(1, len(sorted_trades)):
            if sorted_trades[i]["is_win"] == first_result:
                streak_count += 1
            else:
                break
        
        current_streak = {"type": streak_type, "count": streak_count}
    
    # Add summary data
    summary = {
        "best_month": best_month,
        "worst_month": worst_month,
        "current_streak_type": current_streak.get("type"),
        "current_streak_count": current_streak.get("count"),
        "current_drawdown": round(dd_info.get("current_drawdown_pct", 0.0), 2),
        "peak_equity": round(dd_info.get("peak_equity", 0.0), 2),
        "current_equity": round(dd_info.get("current_equity", 0.0), 2),
        "total_trades": len(closed_trades),
    }
    
    # Create DataFrame
    df = pd.DataFrame(export_records)
    
    # Add summary as additional rows or metadata
    # For CSV, we'll add summary as a comment or separate section
    
    # Export to requested format
    buffer = io.BytesIO()
    if format == "csv":
        # Write summary header
        summary_lines = [
            "# Monthly Performance Report Summary",
            f"# Best Month: {summary['best_month']['month'] if summary['best_month'] else 'N/A'} ({summary['best_month']['return_pct'] if summary['best_month'] else 0}%)",
            f"# Worst Month: {summary['worst_month']['month'] if summary['worst_month'] else 'N/A'} ({summary['worst_month']['return_pct'] if summary['worst_month'] else 0}%)",
            f"# Current Streak: {summary['current_streak_type']} ({summary['current_streak_count']})",
            f"# Current Drawdown: {summary['current_drawdown']}%",
            f"# Peak Equity: {summary['peak_equity']}",
            f"# Current Equity: {summary['current_equity']}",
            f"# Total Trades: {summary['total_trades']}",
            "",
        ]
        csv_header = "\n".join(summary_lines).encode("utf-8")
        df.to_csv(buffer, index=False, encoding="utf-8")
        csv_data = csv_header + buffer.getvalue()
        content = csv_data
        media_type = "text/csv"
        file_ext = "csv"
    else:  # parquet
        df.to_parquet(buffer, index=False, engine="pyarrow", compression="snappy")
        content = buffer.getvalue()
        media_type = "application/octet-stream"
        file_ext = "parquet"
    
    # Get metadata
    code_commit = get_git_commit_hash()
    dataset_hash = get_dataset_version_hash()
    params_hash = get_params_digest()
    
    metadata = {
        "commit_hash": code_commit,
        "dataset_hash": dataset_hash,
        "params_hash": params_hash,
    }
    
    # Calculate hashes
    md5_hash = calculate_file_md5(content)
    sha256_hash = calculate_file_sha256(content)
    
    # Create audit record
    with SessionLocal() as db:
        export_audit = ExportAuditORM(
            filters={"type": "monthly_report"},
            format=format,
            record_count=len(export_records),
            file_hash=sha256_hash,
            file_size_bytes=len(content),
            export_params={**metadata, "summary": summary},
        )
        db.add(export_audit)
        db.commit()
        logger.info(f"Monthly report export recorded: {export_audit.id}, {len(export_records)} records, format={format}")
    
    # Generate filename
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"monthly_report_{timestamp}.{file_ext}"
    
    # Create response with headers
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-MD5": md5_hash,
            "X-Export-Metadata": str(metadata),
            "X-Export-Record-Count": str(len(export_records)),
            "X-Export-File-Hash": sha256_hash,
            "X-Export-Type": "monthly_report",
        },
    )


@router.get("/metrics")
async def get_daily_kpis(lookback_days: int = Query(30, ge=1, le=365, description="Number of days to look back")):
    """
    Get daily KPIs: win-rate 30d, avg RR, DD, HOLD count.
    
    Returns real-time KPI metrics calculated from recent recommendations.
    """
    try:
        kpis = kpis_service.calculate_daily_kpis(lookback_days=lookback_days)
        return {
            "status": "success",
            "kpis": kpis,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to calculate daily KPIs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/export")
async def export_daily_kpis(
    format: str = Query("json", regex="^(json|csv)$", description="Export format"),
    lookback_days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
):
    """
    Export daily KPI report in JSON or CSV format.
    
    Returns downloadable file with KPI metrics.
    """
    from fastapi.responses import Response
    
    try:
        report = kpis_service.generate_report(format=format, lookback_days=lookback_days)
        
        return Response(
            content=report["content"],
            media_type=report["media_type"],
            headers={
                "Content-Disposition": f'attachment; filename="{report["filename"]}"',
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export daily KPIs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

