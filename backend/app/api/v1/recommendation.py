"""Recommendation endpoints."""
from typing import Optional

from io import BytesIO

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import StreamingResponse, JSONResponse

from app.core.database import SessionLocal
from app.core.logging import logger
from app.core.config import settings
from app.core.exceptions import DataGapError, RiskValidationError
from app.db.models import RecommendationORM
from app.models.recommendation import (
    RecommendationResponse,
    RecommendationHistoryResponse,
    RecommendationFallbackResponse,
    SignalPerformanceResponse,
)
from app.services.recommendation_service import RecommendationService
from app.backtesting.risk_sizing import RiskSizer
from app.utils.worm_storage import WormRepository
from sqlalchemy import select
from app.core import pipeline_state

router = APIRouter()
recommendation_service = RecommendationService()


@router.post("/generate", response_model=RecommendationResponse)
async def generate_recommendation(
    user_id: Optional[str] = None,
):
    """
    Generate a new recommendation on-demand (replay mode).
    
    This endpoint triggers immediate signal generation and caches the result.
    Intended for dev/paper trading environments where on-demand generation is needed.
    
    The generated recommendation is stored in the database and cache, making it
    available via the /today endpoint and other endpoints immediately.
    
    **Security**: This endpoint only works if ALLOW_MANUAL_REPLAY is enabled in configuration.
    In production, this should be False to rely on scheduled jobs only.
    
    Args:
        user_id: Optional user ID for personalized position sizing
    
    Returns:
        Generated recommendation response
    
    Raises:
        HTTPException 403: If manual replay is not enabled in configuration
        HTTPException 400: If capital is missing or validation fails
        HTTPException 503: If data is stale/gaps or insufficient history (in production)
        HTTPException 422: If recommendation generation fails
    """
    from app.core.config import settings
    
    # Validate that manual replay is enabled
    if not settings.ALLOW_MANUAL_REPLAY:
        raise HTTPException(
            status_code=403,
            detail={
                "status": "manual_replay_disabled",
                "reason": "Manual replay mode is not enabled. Set ALLOW_MANUAL_REPLAY=True in configuration to enable on-demand generation.",
            },
        )
    
    try:
        # Force generation with allow_replay=True
        data = await recommendation_service.get_today_recommendation(user_id=user_id, allow_replay=True)
        if not data:
            raise HTTPException(
                status_code=422,
                detail={
                    "status": "generation_failed",
                    "reason": "Recommendation generation returned no data",
                },
            )
        # Handle various error statuses similar to GET /today
        if data.get("status") == "capital_missing":
            raise HTTPException(
                status_code=400,
                detail={
                    "status": "capital_missing",
                    "reason": data.get("reason", "Capital validation required"),
                    "requires_capital_input": data.get("requires_capital_input", True),
                },
            )
        if data.get("status") == "data_stale":
            raise HTTPException(
                status_code=503,
                detail={
                    "status": "data_stale",
                    "reason": data.get("reason", "Data is stale"),
                    "interval": data.get("interval"),
                    "latest_timestamp": data.get("latest_timestamp"),
                    "threshold_minutes": data.get("threshold_minutes"),
                },
            )
        if data.get("status") == "data_gaps":
            raise HTTPException(
                status_code=503,
                detail={
                    "status": "data_gaps",
                    "reason": data.get("reason", "Data gaps detected"),
                    "interval": data.get("interval"),
                    "gaps": data.get("gaps", []),
                    "tolerance_candles": data.get("tolerance_candles"),
                },
            )
        if data.get("status") == "insufficient_history":
            # Problem 2: If fallback is enabled, don't raise 503 - let the service's fallback logic handle it
            # The service's get_today_recommendation should already apply fallback when HOLD_FALLBACK_TO_LAST_SIGNAL is True
            # If we're here, the signal is likely HOLD and we should check if fallback was applied
            signal = data.get("signal", "").upper()
            
            # If fallback is enabled and we have a valid signal (even if stale), allow it through
            if settings.HOLD_FALLBACK_TO_LAST_SIGNAL and signal in ("BUY", "SELL", "HOLD"):
                # Check if fallback was applied (is_stale indicates last valid signal was used)
                if data.get("is_stale") or (signal in ("BUY", "SELL")):
                    # Fallback was applied or we have a valid signal - continue to return it
                    logger.info(
                        f"insufficient_history detected but fallback enabled; returning {'stale' if data.get('is_stale') else 'current'} signal",
                        extra={"signal": signal, "is_stale": data.get("is_stale")}
                    )
                    # Continue to return the response below - don't raise 503
                elif signal == "HOLD":
                    # HOLD signal without fallback - check if we can still return it with metadata
                    # This allows UI to show the HOLD state instead of error
                    logger.info(
                        "insufficient_history: returning HOLD signal with metadata for UI display",
                        extra={"signal": signal}
                    )
                    # Continue to return HOLD response with metadata
            else:
                # Fallback not enabled - raise 503 as before
                raise HTTPException(
                    status_code=503,
                    detail={
                        "status": "insufficient_history",
                        "reason": data.get("reason", "Insufficient performance history for risk assessment"),
                        "required_trades": data.get("risk_metrics", {})
                        .get("shutdown_status", {})
                        .get("required_trades"),
                        "lookback_trades": data.get("risk_metrics", {})
                        .get("shutdown_status", {})
                        .get("lookback_trades"),
                        "message": data.get(
                            "message",
                            "Se necesitan más trades históricos para generar una recomendación con métricas de riesgo válidas.",
                        ),
                    },
                )
        if data.get("status") == "no_data":
            raise HTTPException(
                status_code=422,
                detail={
                    "status": "generation_failed",
                    "reason": data.get("reason", "No data available for generation"),
                },
            )
        if data.get("status") == "invalid":
            raise HTTPException(status_code=422, detail=data.get("reason", "Invalid recommendation"))
        
        # Return successful recommendation
        return RecommendationResponse(
            signal=data["signal"],
            entry_range=data["entry_range"],
            stop_loss_take_profit=data["stop_loss_take_profit"],
            confidence=data["confidence"],
            confidence_raw=data.get("confidence_raw", data["confidence"]),
            current_price=data["current_price"],
            analysis=data["analysis"],
            indicators=data["indicators"],
            risk_metrics=data["risk_metrics"],
            factors=data.get("factors", {}),
            signal_breakdown=data.get("signal_breakdown", {}),
            timestamp=data["timestamp"],
            status=data.get("status", "closed"),
            opened_at=data.get("opened_at"),
            closed_at=data.get("closed_at"),
            exit_reason=data.get("exit_reason"),
            exit_price=data.get("exit_price"),
            exit_price_pct=data.get("exit_price_pct"),
            recommended_risk_fraction=data.get("recommended_risk_fraction"),
            recommended_position_size=data.get("recommended_position_size"),
            risk_pct=data.get("risk_pct"),
            capital_assumed=data.get("capital_assumed"),
            disclaimer=data.get("disclaimer", "This is not financial advice. Trading cryptocurrencies involves significant risk."),
            suggested_sizing=data.get("suggested_sizing"),
            backtest_run_id=data.get("backtest_run_id"),
            backtest_cagr=data.get("backtest_cagr"),
            backtest_win_rate=data.get("backtest_win_rate"),
            backtest_risk_reward_ratio=data.get("backtest_risk_reward_ratio"),
            backtest_max_drawdown=data.get("backtest_max_drawdown"),
            backtest_slippage_bps=data.get("backtest_slippage_bps"),
            tracking_error_bps=data.get("tracking_error_bps"),
            execution_plan=data.get("execution_plan"),
            is_stale=data.get("is_stale", False),
            fallback_cause=data.get("fallback_cause"),
            original_signal_date=data.get("original_signal_date"),
        )
    except HTTPException:
        raise
    except RiskValidationError as e:
        if e.audit_type == "daily_risk_limit_exceeded":
            raise HTTPException(
                status_code=400,
                detail={
                    "status": "daily_risk_limit_exceeded",
                    "reason": e.reason,
                    "context_data": e.context_data,
                },
            )
        else:
            raise HTTPException(
                status_code=400,
                detail={
                    "status": "capital_missing",
                    "reason": e.reason,
                    "requires_capital_input": True,
                },
            )
    except Exception as e:
        logger.exception("Error generating recommendation on-demand")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/today", response_model=RecommendationResponse | RecommendationFallbackResponse)
async def get_today_recommendation(
    user_id: Optional[str] = None,
    allow_replay: bool = Query(False, description="Allow on-demand generation (for replays/testing only)"),
):
    """
    Get today's trading recommendation.

    Returns signal, entry range, SL/TP, confidence, indicators, risk metrics, factors, and analysis.
    Position sizing is personalized if user_id is provided.

    By default, only returns existing recommendations from the scheduled daily pipeline.
    Signal generation is deterministic and runs via the scheduled job at 12:00 UTC.

    **Security**: The allow_replay parameter only works if ALLOW_MANUAL_REPLAY is enabled in configuration.
    In production, this should be False to rely on scheduled jobs only.

    Args:
        user_id: Optional user ID for personalized position sizing based on portfolio data
        allow_replay: If True, allows on-demand generation (for replays/testing only) - requires ALLOW_MANUAL_REPLAY=True
    """
    from app.core.config import settings
    
    # Validate that manual replay is enabled if requested
    if allow_replay and not settings.ALLOW_MANUAL_REPLAY:
        raise HTTPException(
            status_code=403,
            detail={
                "status": "manual_replay_disabled",
                "reason": "Manual replay mode is not enabled. Set ALLOW_MANUAL_REPLAY=True in configuration to enable on-demand generation.",
            },
        )
    
    # If the startup pipeline is still running, surface a non-blocking status so the frontend
    # can keep polling instead of timing out.
    if pipeline_state.is_running():
        status = pipeline_state.get_status().to_dict()
        return JSONResponse(
            status_code=202,
            content={
                "status": "processing",
                "reason": "Startup pipeline en ejecución. Vuelve a intentar en unos momentos.",
                "pipeline": status,
            },
        )

    try:
        data = await recommendation_service.get_today_recommendation(user_id=user_id, allow_replay=allow_replay)
        if not data:
            return RecommendationFallbackResponse(
                status="no_data",
                reason="No recommendations have been generated yet.",
                allow_replay_hint=allow_replay,
                data_recency={"status": "missing"},
            )
        # Handle capital_missing status - return it as part of response for UI handling
        if data.get("status") == "capital_missing":
            # Return a response that includes the capital_missing status
            # The frontend will handle displaying the banner/disabled button
            raise HTTPException(
                status_code=400,
                detail={
                    "status": "capital_missing",
                    "reason": data.get("reason", "Capital validation required"),
                    "requires_capital_input": data.get("requires_capital_input", True),
                },
            )
        if data.get("status") == "data_stale":
            raise HTTPException(
                status_code=503,
                detail={
                    "status": "data_stale",
                    "reason": data.get("reason", "Data is stale"),
                    "interval": data.get("interval"),
                    "latest_timestamp": data.get("latest_timestamp"),
                    "threshold_minutes": data.get("threshold_minutes"),
                },
            )
        if data.get("status") == "data_gaps":
            raise HTTPException(
                status_code=503,
                detail={
                    "status": "data_gaps",
                    "reason": data.get("reason", "Data gaps detected"),
                    "interval": data.get("interval"),
                    "gaps": data.get("gaps", []),
                    "tolerance_candles": data.get("tolerance_candles"),
                },
            )
        if data.get("status") == "insufficient_history":
            # In dev/test the pipeline can return an insufficient history guardrail without
            # the fields required by RecommendationResponse (entry_range, SL/TP, etc.).
            # Return a structured error instead of falling through and triggering a 500/422.
            raise HTTPException(
                status_code=503,
                detail={
                    "status": "insufficient_history",
                    "reason": data.get("reason", "Insufficient performance history for risk assessment"),
                    "required_trades": data.get("risk_metrics", {})
                    .get("shutdown_status", {})
                    .get("required_trades"),
                    "lookback_trades": data.get("risk_metrics", {})
                    .get("shutdown_status", {})
                    .get("lookback_trades"),
                    "message": data.get(
                        "message",
                        "Se necesitan más trades históricos para generar una recomendación con métricas de riesgo válidas.",
                    ),
                },
            )
        if data.get("status") == "no_data":
            return RecommendationFallbackResponse(**data)
        if data.get("status") == "invalid":
            raise HTTPException(status_code=422, detail=data.get("reason", "Invalid recommendation"))
        return RecommendationResponse(
            signal=data["signal"],
            entry_range=data["entry_range"],
            stop_loss_take_profit=data["stop_loss_take_profit"],
            confidence=data["confidence"],
            confidence_raw=data.get("confidence_raw", data["confidence"]),
            current_price=data["current_price"],
            analysis=data["analysis"],
            indicators=data["indicators"],
            risk_metrics=data["risk_metrics"],
            factors=data.get("factors", {}),
            signal_breakdown=data.get("signal_breakdown", {}),
            timestamp=data["timestamp"],
            status=data.get("status", "closed"),
            opened_at=data.get("opened_at"),
            closed_at=data.get("closed_at"),
            exit_reason=data.get("exit_reason"),
            exit_price=data.get("exit_price"),
            exit_price_pct=data.get("exit_price_pct"),
            recommended_risk_fraction=data.get("recommended_risk_fraction"),
            recommended_position_size=data.get("recommended_position_size"),
            risk_pct=data.get("risk_pct"),
            capital_assumed=data.get("capital_assumed"),
            disclaimer=data.get("disclaimer", "This is not financial advice. Trading cryptocurrencies involves significant risk."),
            suggested_sizing=data.get("suggested_sizing"),
            backtest_run_id=data.get("backtest_run_id"),
            backtest_cagr=data.get("backtest_cagr"),
            backtest_win_rate=data.get("backtest_win_rate"),
            backtest_risk_reward_ratio=data.get("backtest_risk_reward_ratio"),
            backtest_max_drawdown=data.get("backtest_max_drawdown"),
            backtest_slippage_bps=data.get("backtest_slippage_bps"),
            tracking_error_bps=data.get("tracking_error_bps"),
            execution_plan=data.get("execution_plan"),
            is_stale=data.get("is_stale", False),
            fallback_cause=data.get("fallback_cause"),
            original_signal_date=data.get("original_signal_date"),
        )
    except HTTPException:
        raise
    except RiskValidationError as e:
        # Convert RiskValidationError to proper API response
        # Determine status based on audit_type
        if e.audit_type == "daily_risk_limit_exceeded":
            raise HTTPException(
                status_code=400,
                detail={
                    "status": "daily_risk_limit_exceeded",
                    "reason": e.reason,
                    "context_data": e.context_data,
                },
            )
        else:
            # Default to capital_missing for other risk validation errors
            raise HTTPException(
                status_code=400,
                detail={
                    "status": "capital_missing",
                    "reason": e.reason,
                    "requires_capital_input": True,
                },
            )
    except Exception as e:
        # BE-SIGNAL-01: Surface a structured generation_failed payload instead of a raw 500
        logger.exception("Error fetching today's recommendation")
        # Try to include recency metadata if available
        fallback = {
            "status": "generation_failed",
            "reason": str(e) or "Recommendation generation failed. Check backend logs for details.",
            "latest_available_timestamp": None,
            "latest_available_date": None,
            "data_recency": {"status": "unknown", "as_of": None, "days_since_release": None},
            "allow_replay_hint": settings.ALLOW_MANUAL_REPLAY,
        }
        return RecommendationFallbackResponse(**fallback)


@router.get("/{recommendation_id}/snapshot")
async def get_recommendation_snapshot(recommendation_id: int):
    """
    Get immutable snapshot and verification hashes for a recommendation.

    Returns the full snapshot with code_commit, dataset_hash, and params_hash
    for independent verification.
    """
    with SessionLocal() as db:
        stmt = select(RecommendationORM).where(RecommendationORM.id == recommendation_id)
        rec = db.execute(stmt).scalars().first()
        if not rec:
            raise HTTPException(status_code=404, detail="Recommendation not found")

        # Get snapshot from WORM storage if available
        worm_repo = WormRepository()
        worm_snapshot = None
        if rec.snapshot_json and rec.snapshot_json.get("worm_uuid"):
            try:
                worm_snapshot = worm_repo.read_snapshot(uuid=rec.snapshot_json["worm_uuid"])
            except Exception as e:
                logger.warning(f"Failed to read WORM snapshot: {e}", exc_info=True)

        # Calculate snapshot hash for integrity verification
        from app.utils.hashing import calculate_file_sha256
        import json
        snapshot_hash = ""
        if rec.snapshot_json:
            try:
                snapshot_str = json.dumps(rec.snapshot_json, sort_keys=True, default=str)
                snapshot_hash = calculate_file_sha256(snapshot_str.encode())
            except Exception:
                pass
        
        # Extract execution metrics from snapshot
        execution_metrics = {}
        if rec.snapshot_json:
            snapshot = rec.snapshot_json
            if "execution_stats" in snapshot:
                exec_stats = snapshot["execution_stats"]
                execution_metrics = {
                    "fill_quality": {
                        "fill_rate": exec_stats.get("fill_rate"),
                        "partial_fills": exec_stats.get("partial_fills", 0),
                        "rejected_orders": exec_stats.get("rejected_orders", 0),
                    },
                    "orderbook_fallback_count": exec_stats.get("orderbook_fallback_count"),
                }
        
        # Calculate tracking error if available
        tracking_error = None
        if rec.exit_price and rec.exit_reason:
            target_price = None
            if rec.exit_reason.upper() in ("TP", "TAKE_PROFIT", "take_profit"):
                target_price = rec.take_profit
            elif rec.exit_reason.upper() in ("SL", "STOP_LOSS", "stop_loss"):
                target_price = rec.stop_loss
            
            if target_price and target_price > 0:
                tracking_error_pct = abs((rec.exit_price - target_price) / target_price) * 100.0
                tracking_error = {
                    "tracking_error_pct": round(tracking_error_pct, 4),
                    "tracking_error_bps": round(tracking_error_pct * 100.0, 2),
                }
        
        # Prepare response
        snapshot_data = {
            "recommendation_id": rec.id,
            "date": rec.date,
            "timestamp": rec.created_at.isoformat(),
            "code_commit": rec.code_commit,
            "dataset_hash": rec.dataset_version,
            "params_hash": rec.params_digest,
            "config_version": rec.config_version,
            "snapshot_json": rec.snapshot_json,
            "snapshot_hash": snapshot_hash,
            "has_worm": bool(rec.snapshot_json and rec.snapshot_json.get("worm_uuid")),
            "execution_metrics": execution_metrics if execution_metrics else None,
            "tracking_error": tracking_error,
        }

        if worm_snapshot:
            snapshot_data["worm_snapshot"] = {
                "uuid": worm_snapshot.get("uuid"),
                "path": rec.snapshot_json.get("worm_path"),
                "hash": rec.snapshot_json.get("worm_hash"),
                "timestamp": worm_snapshot.get("timestamp"),
                "payload": worm_snapshot.get("payload"),
                "metadata": worm_snapshot.get("metadata"),
            }

        return snapshot_data


@router.get("/performance", response_model=SignalPerformanceResponse)
async def get_signal_performance(lookahead_days: int = 5, limit: int = 90):
    try:
        data = await recommendation_service.get_signal_performance(
            lookahead_days=lookahead_days,
            limit=limit,
        )
        return SignalPerformanceResponse(**data)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/history", response_model=RecommendationHistoryResponse)
async def get_recommendation_history(
    limit: int = Query(25, ge=1, description="Max rows to return"),
    cursor: str | None = Query(None, description="Opaque cursor for pagination"),
    start_date: str | None = Query(None, description="ISO date (YYYY-MM-DD) inclusive"),
    end_date: str | None = Query(None, description="ISO date (YYYY-MM-DD) inclusive"),
    signal: str | None = Query(None, description="Filter by signal type (BUY|SELL|HOLD)"),
    result: str | None = Query(None, description="Filter by exit result (TP|SL|EXIT)"),
    status: str | None = Query(None, description="Filter by trade status"),
    tracking_error_min: float | None = Query(None, ge=0.0, description="Min tracking error percentage"),
    tracking_error_max: float | None = Query(None, ge=0.0, description="Max tracking error percentage"),
    format: str | None = Query("json", pattern="^(json|csv)$", description="Response format"),
    include_hold_and_open: bool = Query(False, description="Include HOLD signals and open recommendations (decision-support mode)"),
):
    """
    Get recent recommendation history.

    Returns list of past recommendations with all fields including analysis.
    """
    try:
        if format and format != "json":
            export = await recommendation_service.export_recommendation_history(
                limit=limit,
                cursor=cursor,
                start_date=start_date,
                end_date=end_date,
                signal=signal,
                result=result,
                status=status,
                tracking_error_min=tracking_error_min,
                tracking_error_max=tracking_error_max,
                export_format=format,
            )
            return StreamingResponse(
                BytesIO(export["content"]),
                media_type=export["media_type"],
                headers=export["headers"],
            )

        history = await recommendation_service.get_recommendation_history(
            limit=limit,
            cursor=cursor,
            start_date=start_date,
            end_date=end_date,
            signal=signal,
            result=result,
            status=status,
            tracking_error_min=tracking_error_min,
            tracking_error_max=tracking_error_max,
            include_hold_and_open=include_hold_and_open,
        )
        
        # Add no_trade_diagnostics if available from performance summary
        from app.services.performance_service import get_performance_service
        try:
            perf_service = get_performance_service()
            perf_summary = await perf_service.get_summary(use_cache=True, allow_stale_inputs=True, trigger_backfill=False)
            if perf_summary.get("metrics_status") == "NO_TRADES":
                # no_trade_diagnostics is in metadata
                perf_metadata = perf_summary.get("metadata", {})
                no_trade_diagnostics = perf_metadata.get("no_trade_diagnostics") or perf_summary.get("no_trade_diagnostics")
                if no_trade_diagnostics:
                    history["metadata"] = history.get("metadata", {})
                    history["metadata"]["no_trade_diagnostics"] = no_trade_diagnostics
                    history["metadata"]["no_trade_root_cause"] = no_trade_diagnostics.get("root_cause", "unknown")
                    history["metadata"]["signal_counts"] = no_trade_diagnostics.get("signal_counts", {}) or perf_metadata.get("signal_counts", {})
                    history["metadata"]["rejected_orders_count"] = no_trade_diagnostics.get("rejected_orders_count", 0) or perf_metadata.get("rejected_orders_count", 0)
                elif perf_metadata.get("signal_counts"):
                    # Fallback: use signal_counts from metadata even if no_trade_diagnostics is missing
                    history["metadata"] = history.get("metadata", {})
                    history["metadata"]["signal_counts"] = perf_metadata.get("signal_counts", {})
                    history["metadata"]["rejected_orders_count"] = perf_metadata.get("rejected_orders_count", 0)
                    history["metadata"]["no_trade_root_cause"] = perf_metadata.get("no_trade_root_cause", "unknown")
        except Exception:
            # Don't fail if performance service is unavailable
            pass
        
        return history
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

