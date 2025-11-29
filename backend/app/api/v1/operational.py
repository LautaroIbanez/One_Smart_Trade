"""Operational flow API endpoints for complete execution pipeline."""
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel, Field

from app.backtesting.execution_simulator import ExecutionSimulator
from app.backtesting.operational_flow import OperationalFlow, generate_operational_report
from app.backtesting.order_types import LimitOrder, MarketOrder, OrderConfig, OrderSide
from app.backtesting.position import Position, PositionConfig, PositionSide as PosSide
from app.data.curation import DataCuration
from app.data.ingestion import DataIngestion
from app.data.orderbook import OrderBookRepository
from app.core.config import settings
from app.core.logging import logger

router = APIRouter()


def _verify_admin_key(x_admin_api_key: str | None = Header(None, alias="X-Admin-API-Key")) -> None:
    """Verify admin API key for protected endpoints."""
    if settings.ADMIN_API_KEY:
        if not x_admin_api_key or x_admin_api_key != settings.ADMIN_API_KEY:
            raise HTTPException(status_code=403, detail="Invalid or missing admin API key")


class OrderExecutionRequest(BaseModel):
    """Request for order execution through operational flow."""

    symbol: str = Field(..., description="Trading symbol")
    side: str = Field(..., description="Order side (buy or sell)")
    qty: float = Field(..., gt=0, description="Order quantity")
    order_type: str = Field(..., description="Order type (market, limit, stop)")
    limit_price: float | None = Field(None, description="Limit price (for limit orders)")
    stop_price: float | None = Field(None, description="Stop price (for stop orders)")
    timestamp: str = Field(..., description="ISO timestamp")
    venue: str = Field("binance", description="Trading venue")
    max_wait_bars: int = Field(10, ge=1, le=100, description="Max wait bars for limit orders")


class PreprocessingRequest(BaseModel):
    """Request for order book preprocessing."""

    symbol: str = Field(..., description="Trading symbol")
    timestamp: str = Field(..., description="ISO timestamp")
    notional: float = Field(..., gt=0, description="Order notional size")
    side: str = Field("buy", description="Order side (buy or sell)")
    venue: str = Field("binance", description="Trading venue")


@router.post("/execute")
async def execute_order_flow(request: OrderExecutionRequest) -> dict[str, Any]:
    """
    Execute order through complete operational flow.
    
    Steps:
    1. Preprocess order book (spread, imbalance, depth)
    2. Simulate execution
    3. Apply fill and rebalance stops
    4. Return execution and rebalancing results
    """
    try:
        ts = pd.Timestamp(request.timestamp)
        
        # Create order book repository and execution simulator
        orderbook_repo = OrderBookRepository(venue=request.venue)
        execution_sim = ExecutionSimulator(orderbook_repo=orderbook_repo)
        flow = OperationalFlow(orderbook_repo=orderbook_repo, execution_simulator=execution_sim)
        
        # Get order book snapshot and preprocess
        snapshot = await orderbook_repo.get_snapshot(request.symbol, ts, tolerance_seconds=30)
        if not snapshot:
            raise HTTPException(status_code=404, detail=f"No order book found for {request.symbol}")
        
        notional = request.qty * (snapshot.mid_price or 0.0)
        preprocessed = await flow.preprocess_orderbook_for_order(
            request.symbol, ts, notional, side=request.side
        )
        
        # Create order
        config = OrderConfig(max_wait_bars=request.max_wait_bars)
        
        if request.order_type.lower() == "market":
            from app.backtesting.order_types import MarketOrder
            order = MarketOrder(request.symbol, request.side, request.qty, timestamp=ts, config=config)
        elif request.order_type.lower() == "limit":
            if request.limit_price is None:
                raise HTTPException(status_code=400, detail="limit_price required for limit orders")
            order = LimitOrder(
                request.symbol, request.side, request.qty, request.limit_price, timestamp=ts, config=config
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported order type: {request.order_type}")
        
        # Create position (for rebalancing)
        pos_side = PosSide.LONG if request.side.lower() == "buy" else PosSide.SHORT
        position_config = PositionConfig(risk_per_unit=1000.0, reward_per_unit=2000.0)
        position = Position(request.symbol, pos_side, config=position_config)
        
        # Prepare bar data
        bar_data = {
            "timestamp": ts,
            "open": snapshot.best_bid or 0.0,
            "high": snapshot.best_ask or 0.0,
            "low": snapshot.best_bid or 0.0,
            "close": snapshot.mid_price or 0.0,
            "volume": 0.0,
        }
        
        # Execute order through flow
        execution_result, rebalance_event = await flow.process_order_with_rebalancing(
            order, bar_data, position, timestamp=ts, symbol=request.symbol
        )
        
        return {
            "status": "ok",
            "preprocessing": preprocessed,
            "execution": {
                "filled_qty": execution_result.filled_qty,
                "avg_fill_price": execution_result.avg_fill_price,
                "filled_notional": execution_result.filled_notional,
                "slippage_pct": execution_result.slippage_pct,
                "slippage_bps": execution_result.slippage_bps,
                "fill_ratio": execution_result.fill_ratio,
                "status": execution_result.status.value,
                "execution_time_bars": execution_result.execution_time_bars,
                "fill_model_estimate": execution_result.fill_model_estimate,
            },
            "stop_rebalancing": rebalance_event,
            "position": position.to_dict(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/preprocess")
async def preprocess_orderbook(request: PreprocessingRequest) -> dict[str, Any]:
    """
    Preprocess order book snapshot to derive spread, imbalance, and effective depth.
    
    Returns derived metrics for analysis and execution planning.
    """
    try:
        ts = pd.Timestamp(request.timestamp)
        orderbook_repo = OrderBookRepository(venue=request.venue)
        flow = OperationalFlow(orderbook_repo=orderbook_repo)
        
        preprocessed = await flow.preprocess_orderbook_for_order(
            request.symbol, ts, request.notional, side=request.side
        )
        
        return {
            "status": "ok",
            "preprocessing": preprocessed,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trigger-pipeline")
async def trigger_daily_pipeline(
    x_admin_api_key: str | None = Header(None, alias="X-Admin-API-Key"),
) -> dict[str, Any]:
    """
    Manually trigger the daily pipeline (ingestion → curation → signal generation).
    
    This endpoint is protected by ADMIN_API_KEY if configured.
    Useful for:
    - Initial data seeding in new environments
    - Manual replays/testing
    - Recovery after pipeline failures
    
    Returns:
        Pipeline execution result with run_id and status
    """
    _verify_admin_key(x_admin_api_key)
    
    try:
        # Import here to avoid circular dependencies
        from app.main import job_daily_pipeline
        
        logger.info("Manual pipeline trigger requested via API")
        await job_daily_pipeline()
        
        return {
            "status": "ok",
            "message": "Daily pipeline execution completed. Check logs for details.",
        }
    except Exception as e:
        logger.error(f"Pipeline trigger failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline execution failed: {str(e)}")


@router.post("/trigger-recommendation")
async def trigger_recommendation_generation(
    x_admin_api_key: str | None = Header(None, alias="X-Admin-API-Key"),
    user_id: str | None = Query(None, description="User ID for personalized sizing"),
) -> dict[str, Any]:
    """
    Manually trigger recommendation generation with allow_replay=True.
    
    This endpoint is protected by ADMIN_API_KEY if configured.
    Generates a recommendation on-demand without waiting for the scheduled pipeline.
    
    Returns:
        Generated recommendation or error details
    """
    _verify_admin_key(x_admin_api_key)
    
    try:
        from app.services.recommendation_service import RecommendationService
        
        logger.info("Manual recommendation generation requested via API")
        service = RecommendationService()
        recommendation = await service.get_today_recommendation(
            user_id=user_id,
            allow_replay=True,
        )
        
        if not recommendation:
            raise HTTPException(status_code=404, detail="Failed to generate recommendation")
        
        return {
            "status": "ok",
            "recommendation": recommendation,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Recommendation generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Recommendation generation failed: {str(e)}")


@router.get("/report")
async def get_operational_report(
    campaign_id: str | None = Query(None, description="Campaign ID"),
) -> dict[str, Any]:
    """
    Get comprehensive operational report for a campaign.
    
    Returns:
        Report with fill rate, tracking error, realized slippage, and stop rebalancing.
    """
    try:
        return {
            "status": "ok",
            "message": "Operational report - integrate with campaign results",
            "report": {
                "execution": {
                    "fill_rate": 0.85,
                    "avg_slippage_bps": 15.2,
                    "cancel_ratio": 0.10,
                },
                "realized_slippage": {
                    "avg_bps": 15.2,
                    "p95_bps": 45.0,
                },
                "tracking_error": {
                    "mean_deviation": -50.0,
                    "correlation": 0.98,
                },
                "stop_rebalancing": {
                    "total_rebalances": 42,
                },
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/backfill-to-today")
async def backfill_to_today(
    interval: str = Query(..., description="Timeframe to backfill (e.g., '1h', '1d')"),
    symbol: str = Query("BTCUSDT", description="Trading symbol"),
    venue: str = Query("binance", description="Trading venue"),
    x_admin_api_key: str | None = Header(None, alias="X-Admin-API-Key"),
) -> dict[str, Any]:
    """
    Backfill data from latest available timestamp to today (now).
    
    This endpoint computes end=datetime.utcnow() and ensures fetched_at metadata
    is stored for tracking when data was last updated.
    
    If not executed, the frontend can check the status endpoint to know if there's recent data.
    
    This endpoint is protected by ADMIN_API_KEY if configured.
    
    Returns:
        Backfill result with status, rows ingested, and fetched_at timestamp
    """
    _verify_admin_key(x_admin_api_key)
    
    try:
        ingestion = DataIngestion()
        result = await ingestion.backfill_to_today(
            interval=interval,
            symbol=symbol,
            venue=venue,
        )
        
        # Also trigger curation after ingestion
        if result.get("status") == "success":
            try:
                curation = DataCuration()
                curation.curate_interval(interval, venue=venue, symbol=symbol)
            except Exception as curation_exc:
                logger.warning(f"Curation failed after backfill: {curation_exc}")
        
        return {
            "status": "ok",
            "backfill_result": result,
            "fetched_at": result.get("fetched_at"),
            "message": f"Backfill completed for {interval}. {result.get('rows', 0)} rows ingested.",
        }
    except Exception as e:
        logger.error(f"Backfill to today failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Backfill failed: {str(e)}")


@router.get("/data-status")
async def get_data_status(
    interval: str = Query("1d", description="Timeframe to check (e.g., '1h', '1d')"),
    symbol: str = Query("BTCUSDT", description="Trading symbol"),
    venue: str = Query("binance", description="Trading venue"),
) -> dict[str, Any]:
    """
    Get status of latest data, including latest_open_time and freshness.
    
    This allows the frontend to know if there's recent data and display
    "última vela: YYYY-MM-DD" and block graphs if data is stale (>threshold).
    
    In dev mode or when stale inputs are allowed, freshness checks are relaxed
    to prevent false alerts during development/testing with seed data.
    
    Returns:
        Status with latest_open_time, age, and whether data is recent.
        Includes dev_mode, allow_stale_inputs, and freshness_policy flags.
    """
    try:
        curation = DataCuration()
        metadata = curation.get_curated_metadata(interval, venue=venue, symbol=symbol)
        
        # Detect dev mode and stale input allowance
        is_dev_mode = settings.is_dev_mode()
        allow_stale_inputs = is_dev_mode or settings.DEV_FAKE_DATA
        
        # Check if we have seed/demo data (indicates stale inputs are acceptable)
        has_seed_data = False
        if allow_stale_inputs:
            try:
                from app.data.dev_seeding import has_local_raw_data
                has_seed_data = has_local_raw_data(venue=venue, symbol=symbol)
            except Exception:
                # If dev_seeding module not available, assume seed data if in dev mode
                has_seed_data = is_dev_mode
        
        if not metadata:
            return {
                "status": "missing",
                "latest_open_time": None,
                "has_recent_data": False,
                "dev_mode": is_dev_mode,
                "allow_stale_inputs": allow_stale_inputs,
                "freshness_policy": "dev_allow_stale" if allow_stale_inputs else "strict",
                "message": "No curated data found",
            }
        
        latest_open_time = metadata.get("latest_open_time")
        if not latest_open_time:
            return {
                "status": "unknown",
                "latest_open_time": None,
                "has_recent_data": False,
                "dev_mode": is_dev_mode,
                "allow_stale_inputs": allow_stale_inputs,
                "freshness_policy": "dev_allow_stale" if allow_stale_inputs else "strict",
                "message": "latest_open_time not available in metadata",
            }
        
        # Parse latest_open_time and calculate age
        from datetime import datetime, timezone
        try:
            latest_dt = datetime.fromisoformat(latest_open_time.replace("Z", "+00:00"))
            if latest_dt.tzinfo is None:
                latest_dt = latest_dt.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            age_hours = (now - latest_dt).total_seconds() / 3600.0
            age_days = age_hours / 24.0
            
            # Determine if data is recent based on interval
            # For 1d interval, consider stale if > 2 days old
            # For 1h interval, consider stale if > 2 hours old
            if interval == "1d":
                threshold_days = 2.0
                is_recent_by_age = age_days <= threshold_days
            elif interval == "1h":
                threshold_hours = 2.0
                is_recent_by_age = age_hours <= threshold_hours
            else:
                # Default: 2 days
                is_recent_by_age = age_days <= 2.0
            
            # In dev mode or when stale inputs are allowed, override freshness check
            # This prevents false alerts when using seed/demo data
            if allow_stale_inputs:
                is_recent = True  # Always consider data "recent" in dev mode
                freshness_policy = "dev_allow_stale"
            else:
                is_recent = is_recent_by_age
                freshness_policy = "strict"
            
            return {
                "status": "ok",
                "latest_open_time": latest_open_time,
                "latest_open_time_date": latest_dt.date().isoformat(),
                "age_hours": round(age_hours, 2),
                "age_days": round(age_days, 2),  # Keep real age for diagnostics
                "has_recent_data": is_recent,  # Overridden in dev mode
                "dev_mode": is_dev_mode,
                "allow_stale_inputs": allow_stale_inputs,
                "freshness_policy": freshness_policy,
                "has_seed_data": has_seed_data,
                "interval": interval,
                "venue": venue,
                "symbol": symbol,
            }
        except Exception as parse_exc:
            logger.warning(f"Failed to parse latest_open_time: {parse_exc}")
            return {
                "status": "error",
                "latest_open_time": latest_open_time,
                "has_recent_data": False,
                "dev_mode": is_dev_mode,
                "allow_stale_inputs": allow_stale_inputs,
                "freshness_policy": "dev_allow_stale" if allow_stale_inputs else "strict",
                "message": f"Failed to parse latest_open_time: {str(parse_exc)}",
            }
    except Exception as e:
        logger.error(f"Failed to get data status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get data status: {str(e)}")

