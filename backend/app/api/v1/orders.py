"""Order execution and simulation API endpoints."""
from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.backtesting.execution_metrics import ExecutionTracker, NoTradeEvent
from app.backtesting.order_types import (
    LimitOrder,
    MarketOrder,
    OrderConfig,
    OrderSide,
    OrderStatus,
    StopOrder,
)
from app.data.fill_model import FillModel
from app.data.orderbook import OrderBookRepository

router = APIRouter()


class OrderRequest(BaseModel):
    """Request model for order creation."""

    symbol: str = Field(..., description="Trading symbol")
    side: str = Field(..., description="Order side (buy or sell)")
    qty: float = Field(..., gt=0, description="Order quantity")
    order_type: str = Field(..., description="Order type (market, limit, stop)")
    limit_price: float | None = Field(None, description="Limit price (for limit orders)")
    stop_price: float | None = Field(None, description="Stop price (for stop orders)")
    max_wait_bars: int = Field(10, ge=1, le=100, description="Maximum bars to wait (for limit orders)")
    stop_trigger_type: str = Field("market", description="Stop trigger type: market or limit")
    venue: str = Field("binance", description="Trading venue")


@router.post("/simulate")
async def simulate_order(
    request: OrderRequest,
    timestamp: str = Query(..., description="ISO timestamp"),
    bar_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Simulate order execution against order book and bar data.
    
    Creates order and attempts to fill it based on current market conditions.
    """
    try:
        ts = pd.Timestamp(timestamp)
        repo = OrderBookRepository(venue=request.venue)
        book = await repo.get_snapshot(request.symbol, ts, tolerance_seconds=10)
        
        # Create order based on type
        config = OrderConfig(max_wait_bars=request.max_wait_bars, stop_trigger_type=request.stop_trigger_type)
        fill_model = FillModel()
        
        if request.order_type.lower() == "market":
            order = MarketOrder(
                request.symbol,
                request.side,
                request.qty,
                timestamp=ts,
                config=config,
                fill_model=fill_model,
            )
        elif request.order_type.lower() == "limit":
            if request.limit_price is None:
                raise HTTPException(status_code=400, detail="limit_price required for limit orders")
            order = LimitOrder(
                request.symbol,
                request.side,
                request.qty,
                request.limit_price,
                timestamp=ts,
                config=config,
                fill_model=fill_model,
            )
        elif request.order_type.lower() == "stop":
            if request.stop_price is None:
                raise HTTPException(status_code=400, detail="stop_price required for stop orders")
            order = StopOrder(
                request.symbol,
                request.side,
                request.qty,
                request.stop_price,
                timestamp=ts,
                config=config,
                fill_model=fill_model,
                limit_price=request.limit_price,
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unknown order type: {request.order_type}")
        
        # Prepare bar data
        if bar_data is None:
            bar_data = {
                "timestamp": ts,
                "open": book.best_bid if book else 0.0,
                "high": book.best_ask if book else 0.0,
                "low": book.best_bid if book else 0.0,
                "close": book.mid_price if book else 0.0,
                "volume": 0.0,
            }
        
        # Attempt to fill order
        result = order.try_fill(bar_data, book)
        
        # Check for no-trade event
        no_trade_event = None
        if result.status == OrderStatus.CANCELLED and order.age >= order.config.max_wait_bars:
            # Order timed out - record as no-trade
            tracker = ExecutionTracker()
            current_price = book.mid_price if book else (bar_data.get("close") if isinstance(bar_data, dict) else 0.0)
            no_trade_event = tracker.record_no_trade(
                order,
                market_price=current_price,
                reason="timeout",
            )
        
        response = {
            "status": "ok",
            "order": order.to_dict(),
            "execution": {
                "filled_qty": result.filled_qty,
                "avg_price": result.avg_price,
                "filled_notional": result.filled_notional,
                "slippage_pct": result.slippage_pct,
                "slippage_bps": result.slippage_bps,
                "status": result.status.value,
                "partial_fills": result.partial_fills,
            },
        }
        
        if no_trade_event:
            response["no_trade_event"] = {
                "timestamp": no_trade_event.timestamp.isoformat(),
                "symbol": no_trade_event.symbol,
                "side": no_trade_event.side,
                "order_type": no_trade_event.order_type,
                "target_price": no_trade_event.target_price,
                "target_qty": no_trade_event.target_qty,
                "filled_qty": no_trade_event.filled_qty,
                "fill_ratio": no_trade_event.fill_ratio,
                "reason": no_trade_event.reason,
                "wait_bars": no_trade_event.actual_wait_bars,
                "max_wait_bars": no_trade_event.max_wait_bars,
            }
        
        return response
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid timestamp format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fill-rate")
async def calculate_fill_rate(
    symbol: str = Query(..., description="Trading symbol"),
    timestamp: str = Query(..., description="ISO timestamp"),
    side: str = Query(..., description="Order side (buy or sell)"),
    qty: float = Query(..., gt=0, description="Order quantity"),
    order_type: str = Query(..., description="Order type (market, limit, stop)"),
    limit_price: float | None = Query(None, description="Limit price"),
    stop_price: float | None = Query(None, description="Stop price"),
    max_wait_bars: int = Query(10, ge=1, le=100, description="Max wait bars for limit orders"),
    venue: str = Query("binance", description="Trading venue"),
    num_simulations: int = Query(100, ge=1, le=1000, description="Number of simulations"),
) -> dict[str, Any]:
    """
    Calculate fill rate statistics by simulating multiple order executions.
    
    Returns average fill rate, slippage distribution, and execution statistics.
    """
    try:
        ts = pd.Timestamp(timestamp)
        repo = OrderBookRepository(venue=venue)
        book = await repo.get_snapshot(symbol, ts, tolerance_seconds=10)
        
        if not book:
            raise HTTPException(status_code=404, detail=f"No order book found for {symbol}")
        
        config = OrderConfig(max_wait_bars=max_wait_bars)
        fill_model = FillModel()
        
        fill_rates = []
        slippages = []
        fill_times = []
        
        for _ in range(num_simulations):
            # Create order
            if order_type.lower() == "market":
                order = MarketOrder(symbol, side, qty, timestamp=ts, config=config, fill_model=fill_model)
            elif order_type.lower() == "limit":
                if limit_price is None:
                    raise HTTPException(status_code=400, detail="limit_price required")
                order = LimitOrder(symbol, side, qty, limit_price, timestamp=ts, config=config, fill_model=fill_model)
            elif order_type.lower() == "stop":
                if stop_price is None:
                    raise HTTPException(status_code=400, detail="stop_price required")
                order = StopOrder(symbol, side, qty, stop_price, timestamp=ts, config=config, fill_model=fill_model, limit_price=limit_price)
            else:
                raise HTTPException(status_code=400, detail=f"Unknown order type: {order_type}")
            
            # Simulate execution
            bar_data = {
                "timestamp": ts,
                "open": book.best_bid or 0.0,
                "high": book.best_ask or 0.0,
                "low": book.best_bid or 0.0,
                "close": book.mid_price or 0.0,
                "volume": 0.0,
            }
            
            result = order.try_fill(bar_data, book)
            
            # Record order and result
            tracker.record_order(order, result)
            
            # Check for no-trade
            if result.status == OrderStatus.CANCELLED and order.age >= max_wait_bars:
                current_price = book.mid_price if book else bar_data.get("close", 0.0)
                tracker.record_no_trade(order, market_price=current_price, reason="timeout")
            
            fill_rates.append(result.filled_qty / qty if qty > 0 else 0.0)
            slippages.append(result.slippage_pct)
            if result.status.value in ["filled", "partially_filled"]:
                fill_times.append(order.age)
        
        return {
            "status": "ok",
            "symbol": symbol,
            "order_type": order_type,
            "side": side,
            "qty": qty,
            "num_simulations": num_simulations,
            "statistics": {
                "avg_fill_rate": float(np.mean(fill_rates)),
                "median_fill_rate": float(np.median(fill_rates)),
                "std_fill_rate": float(np.std(fill_rates)),
                "min_fill_rate": float(np.min(fill_rates)),
                "max_fill_rate": float(np.max(fill_rates)),
                "avg_slippage_pct": float(np.mean(slippages)),
                "median_slippage_pct": float(np.median(slippages)),
                "std_slippage_pct": float(np.std(slippages)),
                "p95_slippage_pct": float(np.percentile(slippages, 95)),
                "p99_slippage_pct": float(np.percentile(slippages, 99)),
                "avg_fill_time_bars": float(np.mean(fill_times)) if fill_times else None,
                "median_fill_time_bars": float(np.median(fill_times)) if fill_times else None,
            },
            "execution_metrics": tracker.calculate_metrics().__dict__,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid timestamp format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

