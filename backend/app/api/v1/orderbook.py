"""Order book API endpoints."""
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from app.data.fill_model import FillModel, FillSimulator
from app.data.orderbook import OrderBookRepository

router = APIRouter()


@router.get("/snapshot")
async def get_orderbook_snapshot(
    symbol: str = Query(..., description="Trading symbol"),
    timestamp: str = Query(..., description="ISO timestamp"),
    venue: str = Query("binance", description="Trading venue"),
    tolerance_seconds: int = Query(5, ge=1, le=60, description="Maximum time difference in seconds"),
) -> dict[str, Any]:
    """
    Get order book snapshot closest to given timestamp.
    
    Returns snapshot with bids, asks, spread, and depth information.
    """
    try:
        ts = pd.Timestamp(timestamp)
        repo = OrderBookRepository(venue=venue)
        snapshot = await repo.get_snapshot(symbol, ts, tolerance_seconds=tolerance_seconds)
        
        if not snapshot:
            raise HTTPException(
                status_code=404,
                detail=f"No snapshot found for {symbol} near {timestamp} (tolerance: {tolerance_seconds}s)",
            )
        
        return {
            "status": "ok",
            "snapshot": {
                "timestamp": snapshot.timestamp.isoformat(),
                "symbol": snapshot.symbol,
                "venue": snapshot.venue,
                "best_bid": snapshot.best_bid,
                "best_ask": snapshot.best_ask,
                "mid_price": snapshot.mid_price,
                "spread": snapshot.spread,
                "spread_pct": snapshot.spread_pct,
                "bids": snapshot.bids,
                "asks": snapshot.asks,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid timestamp format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/spread-depth")
async def get_spread_depth(
    symbol: str = Query(..., description="Trading symbol"),
    timestamp: str = Query(..., description="ISO timestamp"),
    notional: float = Query(..., gt=0, description="Notional value (price * quantity)"),
    venue: str = Query("binance", description="Trading venue"),
    tolerance_seconds: int = Query(5, ge=1, le=60, description="Maximum time difference in seconds"),
) -> dict[str, Any]:
    """
    Get spread and depth information for given notional at timestamp.
    
    Returns bid/ask depth levels, effective spread, and price impact.
    """
    try:
        ts = pd.Timestamp(timestamp)
        repo = OrderBookRepository(venue=venue)
        result = await repo.get_spread_depth(symbol, ts, notional, tolerance_seconds=tolerance_seconds)
        
        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"No snapshot found for {symbol} near {timestamp} (tolerance: {tolerance_seconds}s)",
            )
        
        return {
            "status": "ok",
            **result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid timestamp format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/range")
async def get_orderbook_range(
    symbol: str = Query(..., description="Trading symbol"),
    start: str = Query(..., description="Start ISO timestamp"),
    end: str = Query(..., description="End ISO timestamp"),
    venue: str = Query("binance", description="Trading venue"),
    limit: int = Query(1000, ge=1, le=10000, description="Maximum number of snapshots to return"),
) -> dict[str, Any]:
    """
    Get order book snapshots for a time range.
    
    Returns list of snapshots with basic metrics (spread, mid price).
    """
    try:
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        
        if start_ts >= end_ts:
            raise HTTPException(status_code=400, detail="Start timestamp must be before end timestamp")
        
        repo = OrderBookRepository(venue=venue)
        snapshots = await repo.load(symbol, start_ts, end_ts)
        
        # Limit results
        if len(snapshots) > limit:
            snapshots = snapshots[-limit:]
        
        # Convert to API format
        data = []
        for snapshot in snapshots:
            data.append({
                "timestamp": snapshot.timestamp.isoformat(),
                "best_bid": snapshot.best_bid,
                "best_ask": snapshot.best_ask,
                "mid_price": snapshot.mid_price,
                "spread": snapshot.spread,
                "spread_pct": snapshot.spread_pct,
                "bid_levels": len(snapshot.bids),
                "ask_levels": len(snapshot.asks),
            })
        
        return {
            "status": "ok",
            "symbol": symbol,
            "venue": venue,
            "start": start,
            "end": end,
            "count": len(snapshots),
            "snapshots": data,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid timestamp format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latest")
async def get_latest_orderbook(
    symbol: str = Query(..., description="Trading symbol"),
    venue: str = Query("binance", description="Trading venue"),
) -> dict[str, Any]:
    """Get most recent order book snapshot."""
    try:
        repo = OrderBookRepository(venue=venue)
        snapshot = await repo.get_latest(symbol)
        
        if not snapshot:
            raise HTTPException(status_code=404, detail=f"No order book data found for {symbol}")
        
        return {
            "status": "ok",
            "snapshot": {
                "timestamp": snapshot.timestamp.isoformat(),
                "symbol": snapshot.symbol,
                "venue": snapshot.venue,
                "best_bid": snapshot.best_bid,
                "best_ask": snapshot.best_ask,
                "mid_price": snapshot.mid_price,
                "spread": snapshot.spread,
                "spread_pct": snapshot.spread_pct,
                "levels": snapshot.levels(n_levels=10),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fill-model")
async def calculate_fill_metrics(
    symbol: str = Query(..., description="Trading symbol"),
    timestamp: str = Query(..., description="ISO timestamp"),
    side: str = Query(..., description="Order side (buy or sell)"),
    notional: float = Query(..., gt=0, description="Order notional value"),
    venue: str = Query("binance", description="Trading venue"),
    tolerance_seconds: int = Query(5, ge=1, le=60, description="Maximum time difference in seconds"),
    vol_est: float = Query(0.02, ge=0, le=1, description="Volatility estimate (as decimal, e.g., 0.02 for 2%)"),
    alpha: float = Query(0.001, description="Impact coefficient"),
    beta: float = Query(0.5, description="Volatility coefficient"),
    impact_type: str = Query("linear", description="Impact type (linear or exponential)"),
) -> dict[str, Any]:
    """
    Calculate fill probability and expected slippage for an order.
    
    Uses fill model to estimate execution probability and slippage based on:
    - Order book depth
    - Spread
    - Volatility
    - Order size
    """
    try:
        ts = pd.Timestamp(timestamp)
        repo = OrderBookRepository(venue=venue)
        snapshot = await repo.get_snapshot(symbol, ts, tolerance_seconds=tolerance_seconds)
        
        if not snapshot:
            raise HTTPException(
                status_code=404,
                detail=f"No snapshot found for {symbol} near {timestamp} (tolerance: {tolerance_seconds}s)",
            )
        
        # Create fill model with custom parameters
        fill_model = FillModel(alpha=alpha, beta=beta, impact_type=impact_type)
        
        # Calculate fill probability
        fill_result = fill_model.fill_probability(side, notional, snapshot, vol_est=vol_est)
        
        # Calculate expected slippage
        expected_slippage = fill_model.expected_slippage(side, notional, snapshot, vol_est)
        
        # Simulate execution
        simulator = FillSimulator(fill_model)
        simulation_result = simulator.simulate_execution(side, notional, snapshot, vol_est=vol_est)
        
        return {
            "status": "ok",
            "symbol": symbol,
            "side": side,
            "notional": notional,
            "timestamp": snapshot.timestamp.isoformat(),
            "fill_probability": fill_result["fill_probability"],
            "expected_price": fill_result["expected_price"],
            "target_price": fill_result["target_price"],
            "expected_slippage_pct": fill_result["expected_slippage_pct"],
            "expected_slippage_bps": fill_result["expected_slippage_bps"],
            "utilization_ratio": fill_result["utilization_ratio"],
            "depth_metric": fill_result["depth_metric"],
            "simulation": {
                "filled_notional": simulation_result.filled_notional,
                "avg_fill_price": simulation_result.avg_fill_price,
                "total_slippage_pct": simulation_result.total_slippage_pct,
                "total_slippage_bps": simulation_result.total_slippage_bps,
                "fill_ratio": simulation_result.fill_ratio,
                "partial_fills_count": len(simulation_result.partial_fills),
            },
            "model_parameters": {
                "alpha": alpha,
                "beta": beta,
                "impact_type": impact_type,
                "vol_est": vol_est,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid timestamp format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/optimal-split")
async def calculate_optimal_split(
    symbol: str = Query(..., description="Trading symbol"),
    timestamp: str = Query(..., description="ISO timestamp"),
    side: str = Query(..., description="Order side (buy or sell)"),
    total_notional: float = Query(..., gt=0, description="Total order notional value"),
    venue: str = Query("binance", description="Trading venue"),
    tolerance_seconds: int = Query(5, ge=1, le=60, description="Maximum time difference in seconds"),
    vol_est: float = Query(0.02, ge=0, le=1, description="Volatility estimate"),
    max_splits: int = Query(5, ge=1, le=20, description="Maximum number of splits"),
    min_split_size: float = Query(100.0, gt=0, description="Minimum size per split"),
    alpha: float = Query(0.001, description="Impact coefficient"),
    beta: float = Query(0.5, description="Volatility coefficient"),
) -> dict[str, Any]:
    """
    Calculate optimal order splitting to minimize slippage.
    
    Returns split strategy with expected slippage for each split.
    """
    try:
        ts = pd.Timestamp(timestamp)
        repo = OrderBookRepository(venue=venue)
        snapshot = await repo.get_snapshot(symbol, ts, tolerance_seconds=tolerance_seconds)
        
        if not snapshot:
            raise HTTPException(
                status_code=404,
                detail=f"No snapshot found for {symbol} near {timestamp}",
            )
        
        fill_model = FillModel(alpha=alpha, beta=beta)
        split_result = fill_model.optimal_order_split(
            side,
            total_notional,
            snapshot,
            vol_est=vol_est,
            max_splits=max_splits,
            min_split_size=min_split_size,
        )
        
        return {
            "status": "ok",
            "symbol": symbol,
            "side": side,
            "total_notional": total_notional,
            "timestamp": snapshot.timestamp.isoformat(),
            **split_result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid timestamp format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

