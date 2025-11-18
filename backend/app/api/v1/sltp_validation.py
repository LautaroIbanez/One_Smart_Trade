"""API endpoints for SL/TP validation against historical orderbook data."""
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.services.sltp_validation_service import SLTPValidationService

router = APIRouter()


@router.get("/validate")
async def validate_sltp_levels(
    start_date: str = Query(..., description="Start date (ISO format: YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (ISO format: YYYY-MM-DD)"),
    symbol: str = Query("BTCUSDT", description="Trading symbol"),
    venue: str = Query("binance", description="Trading venue"),
    lookahead_days: int = Query(7, ge=1, le=30, description="Days to look ahead for validation"),
    fulfillment_threshold: float = Query(0.7, ge=0.0, le=1.0, description="Minimum fulfillment rate threshold"),
) -> dict[str, Any]:
    """
    Validate SL/TP levels for recommendations in a date range against historical orderbook data.
    
    Returns validation report with fulfillment metrics and heuristic adjustment recommendations.
    """
    try:
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {str(e)}")
    
    if start_dt >= end_dt:
        raise HTTPException(status_code=400, detail="Start date must be before end date")
    
    service = SLTPValidationService(venue=venue, symbol=symbol)
    
    try:
        report = await service.validate_period(
            start_date=start_dt,
            end_date=end_dt,
            lookahead_days=lookahead_days,
            fulfillment_threshold=fulfillment_threshold,
        )
        
        return {
            "period": {
                "start": report.period_start.isoformat(),
                "end": report.period_end.isoformat(),
            },
            "summary": {
                "total_recommendations": report.total_recommendations,
                "recommendations_validated": report.recommendations_validated,
            },
            "fulfillment_metrics": {
                "sl_fulfillment_rate_pct": round(report.sl_fulfillment_rate, 2),
                "tp_fulfillment_rate_pct": round(report.tp_fulfillment_rate, 2),
                "both_fulfilled_rate_pct": round(report.both_fulfilled_rate, 2),
                "neither_fulfilled_rate_pct": round(report.neither_fulfilled_rate, 2),
            },
            "distance_metrics": {
                "avg_sl_distance_bps": round(report.avg_sl_distance_bps, 2) if report.avg_sl_distance_bps else None,
                "avg_tp_distance_bps": round(report.avg_tp_distance_bps, 2) if report.avg_tp_distance_bps else None,
                "min_sl_distance_bps": round(report.min_sl_distance_bps, 2) if report.min_sl_distance_bps else None,
                "max_sl_distance_bps": round(report.max_sl_distance_bps, 2) if report.max_sl_distance_bps else None,
                "min_tp_distance_bps": round(report.min_tp_distance_bps, 2) if report.min_tp_distance_bps else None,
                "max_tp_distance_bps": round(report.max_tp_distance_bps, 2) if report.max_tp_distance_bps else None,
            },
            "low_fulfillment_recommendations": report.low_fulfillment_recommendations,
            "heuristic_adjustment": {
                "needed": report.heuristic_adjustment_needed,
                "reason": report.adjustment_reason,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


@router.get("/weekly-report")
async def get_weekly_validation_report(
    weeks_back: int = Query(1, ge=1, le=12, description="Number of weeks to look back"),
    symbol: str = Query("BTCUSDT", description="Trading symbol"),
    venue: str = Query("binance", description="Trading venue"),
    fulfillment_threshold: float = Query(0.7, ge=0.0, le=1.0, description="Minimum fulfillment rate threshold"),
) -> dict[str, Any]:
    """
    Generate weekly validation report for SL/TP levels.
    
    Returns report with fulfillment metrics and heuristic adjustment recommendations.
    """
    service = SLTPValidationService(venue=venue, symbol=symbol)
    
    try:
        report = await service.generate_weekly_report(
            weeks_back=weeks_back,
            fulfillment_threshold=fulfillment_threshold,
        )
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")


@router.get("/validate-recommendation/{recommendation_id}")
async def validate_single_recommendation(
    recommendation_id: int,
    symbol: str = Query("BTCUSDT", description="Trading symbol"),
    venue: str = Query("binance", description="Trading venue"),
    lookahead_days: int = Query(7, ge=1, le=30, description="Days to look ahead for validation"),
) -> dict[str, Any]:
    """
    Validate SL/TP levels for a single recommendation against historical orderbook data.
    """
    from app.core.database import SessionLocal
    from app.db.models import RecommendationORM
    from sqlalchemy import select
    
    service = SLTPValidationService(venue=venue, symbol=symbol)
    
    with SessionLocal() as db:
        try:
            stmt = select(RecommendationORM).where(RecommendationORM.id == recommendation_id)
            recommendation = db.execute(stmt).scalars().first()
            
            if not recommendation:
                raise HTTPException(status_code=404, detail=f"Recommendation {recommendation_id} not found")
        finally:
            db.close()
    
    try:
        result = await service.validate_recommendation(
            recommendation,
            lookahead_days=lookahead_days,
        )
        
        if not result:
            raise HTTPException(
                status_code=400,
                detail="Validation failed: recommendation is HOLD or missing SL/TP levels",
            )
        
        return {
            "recommendation_id": result.recommendation_id,
            "signal": result.signal,
            "entry_optimal": result.entry_optimal,
            "stop_loss": result.stop_loss,
            "take_profit": result.take_profit,
            "validation": {
                "sl_touched": result.sl_touched,
                "tp_touched": result.tp_touched,
                "sl_touch_timestamp": result.sl_touch_timestamp.isoformat() if result.sl_touch_timestamp else None,
                "tp_touch_timestamp": result.tp_touch_timestamp.isoformat() if result.tp_touch_timestamp else None,
                "sl_touch_price": result.sl_touch_price,
                "tp_touch_price": result.tp_touch_price,
            },
            "price_range": {
                "min_price_reached": result.min_price_reached,
                "max_price_reached": result.max_price_reached,
            },
            "distances": {
                "sl_distance_bps": round(result.sl_distance_bps, 2) if result.sl_distance_bps else None,
                "tp_distance_bps": round(result.tp_distance_bps, 2) if result.tp_distance_bps else None,
            },
            "metadata": {
                "orderbook_snapshots_checked": result.orderbook_snapshots_checked,
                "validation_window_start": result.validation_window_start.isoformat(),
                "validation_window_end": result.validation_window_end.isoformat(),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")

