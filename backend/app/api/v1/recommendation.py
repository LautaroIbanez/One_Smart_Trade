"""Recommendation endpoints."""
from typing import Optional

from io import BytesIO

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core.database import SessionLocal
from app.core.logging import logger
from app.core.exceptions import RiskValidationError
from app.db.models import RecommendationORM
from app.models.recommendation import (
    RecommendationResponse,
    RecommendationHistoryResponse,
    SignalPerformanceResponse,
)
from app.services.recommendation_service import RecommendationService
from app.backtesting.risk_sizing import RiskSizer
from app.utils.worm_storage import WormRepository
from sqlalchemy import select

router = APIRouter()
recommendation_service = RecommendationService()


@router.get("/today", response_model=RecommendationResponse)
async def get_today_recommendation(user_id: Optional[str] = None):
    """
    Get today's trading recommendation.

    Returns signal, entry range, SL/TP, confidence, indicators, risk metrics, factors, and analysis.
    Position sizing is personalized if user_id is provided.

    Args:
        user_id: Optional user ID for personalized position sizing based on portfolio data
    """
    try:
        data = await recommendation_service.get_today_recommendation(user_id=user_id)
        if not data:
            raise HTTPException(status_code=404, detail="No recommendation available for today")
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
        if data.get("status") == "invalid":
            raise HTTPException(status_code=422, detail=data.get("reason", "Invalid recommendation"))
        return RecommendationResponse(
            signal=data["signal"],
            entry_range=data["entry_range"],
            stop_loss_take_profit=data["stop_loss_take_profit"],
            confidence=data["confidence"],
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
        raise HTTPException(status_code=500, detail=str(e))


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
    limit: int = Query(25, ge=1, le=200),
    cursor: str | None = Query(None, description="Opaque cursor for pagination"),
    start_date: str | None = Query(None, description="ISO date (YYYY-MM-DD) inclusive"),
    end_date: str | None = Query(None, description="ISO date (YYYY-MM-DD) inclusive"),
    signal: str | None = Query(None, description="Filter by signal type (BUY|SELL|HOLD)"),
    result: str | None = Query(None, description="Filter by exit result (TP|SL|EXIT)"),
    status: str | None = Query(None, description="Filter by trade status"),
    tracking_error_min: float | None = Query(None, ge=0.0, description="Min tracking error percentage"),
    tracking_error_max: float | None = Query(None, ge=0.0, description="Max tracking error percentage"),
    format: str | None = Query("json", pattern="^(json|csv)$", description="Response format"),
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
        )
        return history
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

