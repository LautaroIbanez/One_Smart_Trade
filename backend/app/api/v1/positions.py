"""Position management API endpoints."""
from typing import Any

import pandas as pd
from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from app.backtesting.position import Position, PositionConfig, PositionManager, PositionSide
from app.core.config import settings

router = APIRouter()
position_manager = PositionManager()


class PositionRequest(BaseModel):
    """Request model for position operations."""

    symbol: str = Field(..., description="Trading symbol")
    side: str = Field(..., description="Position side (long or short)")
    fill_price: float = Field(..., gt=0, description="Entry fill price")
    qty: float = Field(..., gt=0, description="Position quantity")
    risk_per_unit: float | None = Field(None, description="Risk per unit for SL calculation")
    reward_per_unit: float | None = Field(None, description="Reward per unit for TP calculation")
    risk_reward_ratio: float | None = Field(None, description="Reward/Risk ratio (e.g., 2.0 for 2:1)")
    fixed_stop_loss: float | None = Field(None, description="Fixed stop loss price")
    fixed_take_profit: float | None = Field(None, description="Fixed take profit price")


class PartialFillRequest(BaseModel):
    """Request model for applying partial fills."""

    symbol: str = Field(..., description="Trading symbol")
    fill_price: float = Field(..., gt=0, description="Fill price")
    qty: float = Field(..., gt=0, description="Fill quantity")


@router.post("/open")
async def open_position(request: PositionRequest) -> dict[str, Any]:
    """
    Open a new simulated position or add to existing simulated position.
    
    This endpoint is **paper-only**: it manages positions in memory for backtesting/simulación,
    and no real orders or positions are created on any exchange.
    """
    # BE-LIVE-01: Enforce decision-support only mode for any position operation
    if settings.DISABLE_LIVE_EXECUTION or settings.DECISION_SUPPORT_ONLY:
        raise HTTPException(
            status_code=403,
            detail={
                "status": "paper_only",
                "reason": "Live position management is disabled by DECISION_SUPPORT_ONLY/DISABLE_LIVE_EXECUTION.",
                "message": "Este endpoint sólo gestiona posiciones simuladas para backtesting/decision support. No abre posiciones reales.",
                "disclaimer": "Simulation only. No live positions are managed by this API.",
            },
        )
    try:
        config = PositionConfig(
            risk_per_unit=request.risk_per_unit,
            reward_per_unit=request.reward_per_unit,
            risk_reward_ratio=request.risk_reward_ratio,
            fixed_stop_loss=request.fixed_stop_loss,
            fixed_take_profit=request.fixed_take_profit,
        )
        
        position = position_manager.open_position(
            symbol=request.symbol,
            side=request.side,
            fill_price=request.fill_price,
            qty=request.qty,
            config=config,
        )
        
        return {
            "status": "ok",
            "position": position.to_dict(),
            "levels": {
                "avg_entry": position.avg_entry,
                "stop_loss": position.stop_loss,
                "take_profit": position.take_profit,
                "risk_per_unit": position.risk_per_unit,
                "reward_per_unit": position.reward_per_unit,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/apply-fill")
async def apply_fill(request: PartialFillRequest) -> dict[str, Any]:
    """
    Apply a fill to existing simulated position.
    
    Recalculates average entry price and SL/TP levels automatically (paper-only).
    """
    if settings.DISABLE_LIVE_EXECUTION or settings.DECISION_SUPPORT_ONLY:
        raise HTTPException(
            status_code=403,
            detail={
                "status": "paper_only",
                "reason": "Live position management is disabled by DECISION_SUPPORT_ONLY/DISABLE_LIVE_EXECUTION.",
                "message": "Este endpoint sólo actualiza fills en posiciones simuladas. No afecta ninguna cuenta real.",
                "disclaimer": "Simulation only. No live positions are managed by this API.",
            },
        )
    try:
        position = position_manager.get_position(request.symbol)
        if not position:
            raise HTTPException(status_code=404, detail=f"Position not found for {request.symbol}")
        
        old_entry = position.avg_entry
        old_size = position.size
        
        position.apply_fill(request.fill_price, request.qty)
        
        return {
            "status": "ok",
            "symbol": request.symbol,
            "fill": {
                "price": request.fill_price,
                "qty": request.qty,
                "notional": request.fill_price * request.qty,
            },
            "position_before": {
                "avg_entry": old_entry,
                "size": old_size,
            },
            "position_after": {
                "avg_entry": position.avg_entry,
                "size": position.size,
                "stop_loss": position.stop_loss,
                "take_profit": position.take_profit,
            },
            "recalculated": True,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update-price")
async def update_position_price(
    symbol: str = Query(..., description="Trading symbol"),
    current_price: float = Query(..., gt=0, description="Current market price"),
) -> dict[str, Any]:
    """Update simulated position current price and calculate unrealized P&L (paper-only)."""
    if settings.DISABLE_LIVE_EXECUTION or settings.DECISION_SUPPORT_ONLY:
        raise HTTPException(
            status_code=403,
            detail={
                "status": "paper_only",
                "reason": "Live position management is disabled by DECISION_SUPPORT_ONLY/DISABLE_LIVE_EXECUTION.",
                "message": "Este endpoint sólo actualiza precios y P&L de posiciones simuladas. No afecta ninguna cuenta real.",
                "disclaimer": "Simulation only. No live positions are managed by this API.",
            },
        )
    try:
        position = position_manager.get_position(symbol)
        if not position:
            raise HTTPException(status_code=404, detail=f"Position not found for {symbol}")
        
        position.update_price(current_price)
        exit_check = position.check_exit_conditions()
        
        return {
            "status": "ok",
            "position": position.to_dict(),
            "exit_check": exit_check,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_position_status(symbol: str = Query(..., description="Trading symbol")) -> dict[str, Any]:
    """Get current simulated position status with SL/TP levels (paper-only)."""
    try:
        position = position_manager.get_position(symbol)
        if not position:
            raise HTTPException(status_code=404, detail=f"Position not found for {symbol}")
        
        state = position.get_state()
        
        return {
            "status": "ok",
            "position": position.to_dict(),
            "state": {
                "symbol": state.symbol,
                "side": state.side.value,
                "size": state.size,
                "avg_entry": state.avg_entry,
                "current_price": state.current_price,
                "stop_loss": state.stop_loss,
                "take_profit": state.take_profit,
                "unrealized_pnl": state.unrealized_pnl,
                "unrealized_pnl_pct": state.unrealized_pnl_pct,
                "num_fills": len(state.fills),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/close")
async def close_position(
    symbol: str = Query(..., description="Trading symbol"),
    close_price: float = Query(..., gt=0, description="Close price"),
    partial_qty: float | None = Query(None, gt=0, description="Partial close quantity (if None, closes all)"),
) -> dict[str, Any]:
    """Close simulated position (full or partial, paper-only)."""
    if settings.DISABLE_LIVE_EXECUTION or settings.DECISION_SUPPORT_ONLY:
        raise HTTPException(
            status_code=403,
            detail={
                "status": "paper_only",
                "reason": "Live position management is disabled by DECISION_SUPPORT_ONLY/DISABLE_LIVE_EXECUTION.",
                "message": "Este endpoint sólo cierra posiciones simuladas utilizadas para backtesting/decision support. No cierra posiciones reales.",
                "disclaimer": "Simulation only. No live positions are managed by this API.",
            },
        )
    try:
        result = position_manager.close_position(symbol, close_price, partial_qty=partial_qty)
        
        if result is None:
            raise HTTPException(status_code=404, detail=f"Position not found for {symbol}")
        
        return {
            "status": "ok",
            "symbol": symbol,
            "close_result": result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/all")
async def get_all_positions() -> dict[str, Any]:
    """Get all open simulated positions (paper-only)."""
    try:
        positions = []
        for symbol, position in position_manager.positions.items():
            positions.append(position.to_dict())
        
        return {
            "status": "ok",
            "count": len(positions),
            "positions": positions,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/check-exits")
async def check_exit_conditions(
    prices: dict[str, float] = Body(..., description="Dict of symbol -> current_price"),
) -> dict[str, Any]:
    """
    Check exit conditions for all positions given current prices.
    
    Updates prices and checks if any positions should be closed.
    """
    try:
        position_manager.update_prices(prices)
        exits = position_manager.check_all_exits()
        
        return {
            "status": "ok",
            "exits_found": len(exits),
            "exits": exits,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))





