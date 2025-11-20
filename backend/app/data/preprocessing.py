"""Preprocessing utilities for deriving spread, imbalance, and effective depth from order books."""
from __future__ import annotations

from typing import Any

import pandas as pd

from app.data.orderbook import OrderBookSnapshot


def derive_spread(snapshot: OrderBookSnapshot) -> dict[str, float]:
    """
    Derive spread metrics from order book snapshot.
    
    Returns:
        Dict with spread metrics:
        - absolute_spread: Best ask - best bid
        - relative_spread_pct: Spread as percentage of mid price
        - spread_bps: Spread in basis points
    """
    if snapshot.best_bid is None or snapshot.best_ask is None:
        return {
            "absolute_spread": 0.0,
            "relative_spread_pct": 0.0,
            "spread_bps": 0.0,
        }
    
    absolute_spread = snapshot.best_ask - snapshot.best_bid
    mid_price = snapshot.mid_price
    
    if mid_price > 0:
        relative_spread_pct = (absolute_spread / mid_price) * 100.0
        spread_bps = (absolute_spread / mid_price) * 10000.0
    else:
        relative_spread_pct = 0.0
        spread_bps = 0.0
    
    return {
        "absolute_spread": absolute_spread,
        "relative_spread_pct": relative_spread_pct,
        "spread_bps": spread_bps,
    }


def derive_imbalance(snapshot: OrderBookSnapshot, levels: int = 10) -> dict[str, float]:
    """
    Derive order book imbalance metrics.
    
    Imbalance measures the relative weight of bids vs asks in the order book.
    Positive imbalance indicates more buy pressure, negative indicates sell pressure.
    
    Args:
        snapshot: Order book snapshot
        levels: Number of levels to consider
        
    Returns:
        Dict with imbalance metrics:
        - bid_volume: Total bid volume in top N levels
        - ask_volume: Total ask volume in top N levels
        - imbalance_ratio: (bid_volume - ask_volume) / (bid_volume + ask_volume)
        - imbalance_pct: Imbalance as percentage
    """
    bid_volume = sum(qty for _, qty in snapshot.bids[:levels])
    ask_volume = sum(qty for _, qty in snapshot.asks[:levels])
    total_volume = bid_volume + ask_volume
    
    if total_volume > 0:
        imbalance_ratio = (bid_volume - ask_volume) / total_volume
        imbalance_pct = imbalance_ratio * 100.0
    else:
        imbalance_ratio = 0.0
        imbalance_pct = 0.0
    
    return {
        "bid_volume": bid_volume,
        "ask_volume": ask_volume,
        "total_volume": total_volume,
        "imbalance_ratio": imbalance_ratio,
        "imbalance_pct": imbalance_pct,
    }


def derive_effective_depth(
    snapshot: OrderBookSnapshot,
    notional: float,
    *,
    side: str = "buy",
    levels: int = 10,
) -> dict[str, float]:
    """
    Derive effective depth for a given notional size.
    
    Effective depth indicates how much liquidity is available at or near current prices
    for a given order size. Measures price impact potential.
    
    Args:
        snapshot: Order book snapshot
        notional: Order notional size
        side: Order side ("buy" or "sell")
        levels: Number of levels to consider
        
    Returns:
        Dict with depth metrics:
        - available_depth: Available depth for the notional
        - depth_utilization: notional / available_depth (0-1, >1 means insufficient)
        - avg_price_impact: Average price impact if order consumes depth
        - levels_consumed: Number of levels needed to fill order
    """
    side_lower = side.lower()
    
    if side_lower == "buy":
        levels_data = snapshot.asks[:levels]
        best_price = snapshot.best_ask
    else:  # sell
        levels_data = snapshot.bids[:levels]
        best_price = snapshot.best_bid
    
    if not levels_data or best_price is None:
        return {
            "available_depth": 0.0,
            "depth_utilization": 1.0,
            "avg_price_impact": 0.0,
            "levels_consumed": 0,
        }
    
    # Calculate cumulative depth and price impact
    cumulative_qty = 0.0
    cumulative_notional = 0.0
    levels_consumed = 0
    
    target_qty = notional / best_price if best_price > 0 else 0.0
    
    for price, qty in levels_data:
        if cumulative_qty >= target_qty:
            break
        
        level_qty = min(qty, target_qty - cumulative_qty)
        cumulative_qty += level_qty
        cumulative_notional += price * level_qty
        levels_consumed += 1
    
    available_depth = cumulative_notional if cumulative_notional > 0 else notional
    depth_utilization = min(notional / available_depth, 1.0) if available_depth > 0 else 1.0
    
    # Calculate average price impact
    if cumulative_qty > 0:
        avg_price = cumulative_notional / cumulative_qty
        price_impact = abs((avg_price - best_price) / best_price * 100.0) if best_price > 0 else 0.0
    else:
        price_impact = 0.0
    
    return {
        "available_depth": available_depth,
        "depth_utilization": depth_utilization,
        "avg_price_impact": price_impact,
        "levels_consumed": levels_consumed,
        "can_fill_completely": cumulative_qty >= target_qty,
    }


def preprocess_orderbook_snapshot(
    snapshot: OrderBookSnapshot,
    notional: float | None = None,
    *,
    side: str = "buy",
    depth_levels: int = 10,
) -> dict[str, Any]:
    """
    Preprocess order book snapshot to derive all derived metrics.
    
    Args:
        snapshot: Order book snapshot
        notional: Optional order notional for depth analysis
        side: Order side for depth analysis ("buy" or "sell")
        depth_levels: Number of levels for depth calculation
        
    Returns:
        Dict with all derived metrics:
        - spread metrics (absolute, relative, bps)
        - imbalance metrics (bid_volume, ask_volume, ratio, pct)
        - depth metrics (if notional provided)
    """
    result = {
        "timestamp": snapshot.timestamp.isoformat(),
        "mid_price": snapshot.mid_price,
        "best_bid": snapshot.best_bid,
        "best_ask": snapshot.best_ask,
        **derive_spread(snapshot),
        **derive_imbalance(snapshot, levels=depth_levels),
    }
    
    if notional is not None and notional > 0:
        result["depth"] = derive_effective_depth(snapshot, notional, side=side, levels=depth_levels)
    
    return result


def batch_preprocess_snapshots(
    snapshots: list[OrderBookSnapshot],
    notional: float | None = None,
    *,
    side: str = "buy",
    depth_levels: int = 10,
) -> pd.DataFrame:
    """
    Batch preprocess multiple order book snapshots.
    
    Args:
        snapshots: List of order book snapshots
        notional: Optional order notional for depth analysis
        side: Order side for depth analysis
        depth_levels: Number of levels for depth calculation
        
    Returns:
        DataFrame with preprocessed metrics for each snapshot
    """
    results = [
        preprocess_orderbook_snapshot(snap, notional, side=side, depth_levels=depth_levels)
        for snap in snapshots
    ]
    
    return pd.DataFrame(results)






