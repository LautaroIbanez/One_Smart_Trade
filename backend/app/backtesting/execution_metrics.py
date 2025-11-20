"""Execution metrics and no-trade tracking."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from app.backtesting.order_types import BaseOrder, OrderResult, OrderStatus


@dataclass
class NoTradeEvent:
    """Event representing a missed trade opportunity."""

    timestamp: pd.Timestamp
    symbol: str
    side: str
    order_type: str
    target_price: float
    target_qty: float
    limit_price: float | None = None
    reason: str = "timeout"  # "timeout", "insufficient_depth", "price_moved"
    max_wait_bars: int = 10
    actual_wait_bars: int = 0
    filled_qty: float = 0.0
    fill_ratio: float = 0.0
    market_price_at_timeout: float | None = None
    opportunity_cost: float | None = None  # Potential profit/loss if filled


@dataclass
class ExecutionMetrics:
    """Metrics for execution friction and fill rates."""

    total_orders: int = 0
    filled_orders: int = 0
    partially_filled_orders: int = 0
    cancelled_orders: int = 0
    no_trades: int = 0
    
    fill_rate: float = 0.0  # Filled / Total
    partial_fill_rate: float = 0.0  # Partial / Total
    cancel_ratio: float = 0.0  # Cancelled / Total
    no_trade_ratio: float = 0.0  # No trades / Total
    
    total_qty: float = 0.0
    filled_qty: float = 0.0
    cancelled_qty: float = 0.0
    qty_fill_rate: float = 0.0  # Filled qty / Total qty
    
    avg_wait_bars: float = 0.0
    median_wait_bars: float = 0.0
    p95_wait_bars: float = 0.0
    
    avg_slippage_bps: float = 0.0
    median_slippage_bps: float = 0.0
    p95_slippage_bps: float = 0.0
    
    no_trade_events: list[NoTradeEvent] = field(default_factory=list)
    opportunity_cost: float = 0.0  # Total opportunity cost from missed trades


class ExecutionTracker:
    """
    Tracks execution metrics including fill rates, wait times, and no-trade events.
    
    Records missed opportunities when orders don't fill and calculates execution friction.
    """

    def __init__(self) -> None:
        """Initialize execution tracker."""
        self.orders: list[BaseOrder] = []
        self.order_results: list[OrderResult] = []
        self.no_trade_events: list[NoTradeEvent] = []
        self.wait_times: list[int] = []  # Bars waited for filled orders
        self.slippages_bps: list[float] = []  # Slippage in basis points

    def record_order(self, order: BaseOrder, result: OrderResult | None = None) -> None:
        """
        Record an order execution attempt.
        
        Args:
            order: Order object
            result: Optional order result
        """
        self.orders.append(order)
        
        if result:
            self.order_results.append(result)
            
            # Record metrics for filled orders
            if result.status in [OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED]:
                self.wait_times.append(order.age)
                self.slippages_bps.append(result.slippage_bps)

    def record_no_trade(
        self,
        order: BaseOrder,
        *,
        market_price: float | None = None,
        opportunity_cost: float | None = None,
        reason: str = "timeout",
    ) -> NoTradeEvent:
        """
        Record a no-trade event (order didn't fill sufficiently).
        
        Args:
            order: Order that didn't fill
            market_price: Market price at timeout
            opportunity_cost: Potential profit/loss if filled
            reason: Reason for no-trade
            
        Returns:
            NoTradeEvent with details
        """
        fill_ratio = order.fill_ratio
        
        limit_price = None
        if hasattr(order, "limit_price"):
            limit_price = order.limit_price
        
        target_price = order.avg_fill_price if order.avg_fill_price > 0 else (limit_price or 0.0)
        
        event = NoTradeEvent(
            timestamp=order.timestamp,
            symbol=order.symbol,
            side=order.side.value,
            order_type=order.__class__.__name__,
            target_price=target_price,
            target_qty=order.qty,
            limit_price=limit_price,
            reason=reason,
            max_wait_bars=order.config.max_wait_bars,
            actual_wait_bars=order.age,
            filled_qty=order.filled,
            fill_ratio=fill_ratio,
            market_price_at_timeout=market_price,
            opportunity_cost=opportunity_cost,
        )
        
        self.no_trade_events.append(event)
        return event

    def calculate_metrics(self) -> ExecutionMetrics:
        """
        Calculate execution metrics from tracked orders.
        
        Returns:
            ExecutionMetrics with all calculated metrics
        """
        if not self.orders:
            return ExecutionMetrics()
        
        total_orders = len(self.orders)
        
        # Count order statuses
        filled = sum(1 for r in self.order_results if r.status == OrderStatus.FILLED)
        partially_filled = sum(1 for r in self.order_results if r.status == OrderStatus.PARTIALLY_FILLED)
        cancelled = sum(1 for r in self.order_results if r.status == OrderStatus.CANCELLED)
        no_trades = len(self.no_trade_events)
        
        # Calculate ratios
        fill_rate = filled / total_orders if total_orders > 0 else 0.0
        partial_fill_rate = partially_filled / total_orders if total_orders > 0 else 0.0
        cancel_ratio = cancelled / total_orders if total_orders > 0 else 0.0
        no_trade_ratio = no_trades / total_orders if total_orders > 0 else 0.0
        
        # Quantity metrics
        total_qty = sum(o.qty for o in self.orders)
        filled_qty = sum(r.filled_qty for r in self.order_results)
        cancelled_qty = sum(o.qty - o.filled for o in self.orders if o.status == OrderStatus.CANCELLED)
        qty_fill_rate = filled_qty / total_qty if total_qty > 0 else 0.0
        
        # Wait time statistics
        import numpy as np
        
        avg_wait_bars = float(np.mean(self.wait_times)) if self.wait_times else 0.0
        median_wait_bars = float(np.median(self.wait_times)) if self.wait_times else 0.0
        p95_wait_bars = float(np.percentile(self.wait_times, 95)) if self.wait_times else 0.0
        
        # Slippage statistics
        avg_slippage_bps = float(np.mean(self.slippages_bps)) if self.slippages_bps else 0.0
        median_slippage_bps = float(np.median(self.slippages_bps)) if self.slippages_bps else 0.0
        p95_slippage_bps = float(np.percentile(self.slippages_bps, 95)) if self.slippages_bps else 0.0
        
        # Opportunity cost
        opportunity_cost = sum(e.opportunity_cost or 0.0 for e in self.no_trade_events)
        
        return ExecutionMetrics(
            total_orders=total_orders,
            filled_orders=filled,
            partially_filled_orders=partially_filled,
            cancelled_orders=cancelled,
            no_trades=no_trades,
            fill_rate=fill_rate,
            partial_fill_rate=partial_fill_rate,
            cancel_ratio=cancel_ratio,
            no_trade_ratio=no_trade_ratio,
            total_qty=total_qty,
            filled_qty=filled_qty,
            cancelled_qty=cancelled_qty,
            qty_fill_rate=qty_fill_rate,
            avg_wait_bars=avg_wait_bars,
            median_wait_bars=median_wait_bars,
            p95_wait_bars=p95_wait_bars,
            avg_slippage_bps=avg_slippage_bps,
            median_slippage_bps=median_slippage_bps,
            p95_slippage_bps=p95_slippage_bps,
            no_trade_events=self.no_trade_events.copy(),
            opportunity_cost=opportunity_cost,
        )

    def reset(self) -> None:
        """Reset tracker state."""
        self.orders.clear()
        self.order_results.clear()
        self.no_trade_events.clear()
        self.wait_times.clear()
        self.slippages_bps.clear()






