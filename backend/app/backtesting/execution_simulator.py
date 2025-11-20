"""Execution simulator consuming order books for realistic fills, slippage, and failures."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from app.backtesting.execution_metrics import ExecutionTracker, NoTradeEvent
from app.backtesting.order_types import BaseOrder, LimitOrder, MarketOrder, OrderResult, OrderStatus, StopOrder
from app.backtesting.orderbook_warning import OrderBookWarning
from app.core.logging import logger, sanitize_log_extra
from app.data.fill_model import FillModel, FillModelConfig, FillSimulator, FillSimulationResult
from app.data.orderbook import OrderBookRepository, OrderBookSnapshot


@dataclass
class ExecutionSimulationResult:
    """Result of an execution simulation."""

    filled_qty: float
    avg_fill_price: float
    filled_notional: float
    slippage_pct: float
    slippage_bps: float
    fill_ratio: float
    status: OrderStatus
    partial_fills: list[dict[str, Any]] = field(default_factory=list)
    execution_time_bars: int = 0
    order_book_snapshot: OrderBookSnapshot | None = None
    fill_model_estimate: dict[str, Any] | None = None


class ExecutionSimulator:
    """
    Execution simulator that consumes order books to determine fills, slippage, and failures.
    
    Integrates:
    - Order book snapshots for depth analysis
    - Fill model for slippage estimation
    - Execution tracker for metrics
    - Order types (Market, Limit, Stop) for realistic execution
    """

    def __init__(
        self,
        orderbook_repo: OrderBookRepository | None = None,
        fill_model: FillModel | None = None,
        execution_tracker: ExecutionTracker | None = None,
    ) -> None:
        """
        Initialize execution simulator.
        
        Args:
            orderbook_repo: Order book repository for snapshots
            fill_model: Fill model for slippage estimation
            execution_tracker: Execution tracker for metrics
        """
        self.orderbook_repo = orderbook_repo or OrderBookRepository()
        self.fill_model = fill_model or FillModel()
        self.tracker = execution_tracker or ExecutionTracker()
        self.orderbook_warnings: list[OrderBookWarning] = []
        self.orderbook_fallback_count: int = 0

    async def simulate_execution(
        self,
        order: BaseOrder,
        bar: dict[str, Any] | pd.Series,
        *,
        timestamp: pd.Timestamp | None = None,
        symbol: str | None = None,
    ) -> ExecutionSimulationResult:
        """
        Simulate order execution against order book.
        
        Args:
            order: Order to execute
            bar: Current bar data (OHLCV)
            timestamp: Timestamp for order book lookup (default: bar timestamp)
            symbol: Trading symbol (default: order.symbol)
            
        Returns:
            ExecutionSimulationResult with fill details
        """
        if isinstance(bar, pd.Series):
            bar = bar.to_dict()
        
        timestamp = timestamp or pd.Timestamp(bar.get("timestamp", pd.Timestamp.utcnow()))
        symbol = symbol or order.symbol
        
        # Get order book snapshot
        tolerance_seconds = 30
        book_snapshot = await self.orderbook_repo.get_snapshot(symbol, timestamp, tolerance_seconds=tolerance_seconds)
        
        # Emit warning if orderbook not available before falling back
        if book_snapshot is None:
            reason = "not_found"  # Default reason
            # Check if file exists to provide more specific reason
            try:
                from pathlib import Path
                orderbook_path = self.orderbook_repo._get_orderbook_path(symbol)
                if not orderbook_path.exists():
                    reason = "file_not_found"
                else:
                    # Try to load snapshots to see if within tolerance
                    start = timestamp - pd.Timedelta(seconds=tolerance_seconds)
                    end = timestamp + pd.Timedelta(seconds=tolerance_seconds)
                    snapshots = await self.orderbook_repo.load(symbol, start, end)
                    if not snapshots:
                        reason = "no_snapshots_in_range"
                    else:
                        # Find closest snapshot to check tolerance
                        closest = min(snapshots, key=lambda s: abs((s.timestamp - timestamp).total_seconds()))
                        diff_seconds = abs((closest.timestamp - timestamp).total_seconds())
                        if diff_seconds > tolerance_seconds:
                            reason = "out_of_tolerance"
            except Exception:
                reason = "not_found"
            
            warning = OrderBookWarning(
                symbol=symbol,
                timestamp=timestamp.isoformat(),
                reason=reason,
                tolerance_seconds=tolerance_seconds,
            )
            self.orderbook_warnings.append(warning)
            self.orderbook_fallback_count += 1
            # Warning payloads come from dataclasses—sanitize before logging.
            logger.warning(str(warning), extra=sanitize_log_extra(warning.to_dict()))
        
        # Try to fill order
        result = order.try_fill(bar, book_snapshot)
        
        # Track order execution
        self.tracker.record_order(order, result)
        
        # Check for no-trade if cancelled
        if result.status == OrderStatus.CANCELLED and order.age >= order.config.max_wait_bars:
            current_price = book_snapshot.mid_price if book_snapshot else bar.get("close", 0.0)
            self.tracker.record_no_trade(
                order,
                market_price=current_price,
                reason="timeout" if order.age >= order.config.max_wait_bars else "insufficient_depth",
            )
        
        # Get fill model estimate if order book available
        fill_model_estimate = None
        if book_snapshot and result.filled_qty > 0:
            vol_est = bar.get("atr", 0.0) / bar.get("close", 1.0) if bar.get("close") else 0.02
            side_str = order.side.value
            notional = result.filled_notional
            
            expected_slippage = self.fill_model.expected_slippage(side_str, notional, book_snapshot, vol_est)
            fill_prob = self.fill_model.fill_probability(side_str, notional, book_snapshot, vol_est)
            
            fill_model_estimate = {
                "expected_slippage": expected_slippage,
                "fill_probability": fill_prob,
                "depth_metric": self.fill_model.depth_metric(book_snapshot, side_str),
            }
        
        return ExecutionSimulationResult(
            filled_qty=result.filled_qty,
            avg_fill_price=result.avg_price,
            filled_notional=result.filled_notional,
            slippage_pct=result.slippage_pct,
            slippage_bps=result.slippage_bps,
            fill_ratio=result.filled_qty / order.qty if order.qty > 0 else 0.0,
            status=result.status,
            partial_fills=result.partial_fills,
            execution_time_bars=order.age,
            order_book_snapshot=book_snapshot,
            fill_model_estimate=fill_model_estimate,
        )

    async def simulate_order_sequence(
        self,
        orders: list[BaseOrder],
        bars: list[dict[str, Any] | pd.Series],
        *,
        symbol: str | None = None,
    ) -> list[ExecutionSimulationResult]:
        """
        Simulate execution of multiple orders across bars.
        
        Args:
            orders: List of orders to execute
            bars: List of bar data (should match order count)
            symbol: Trading symbol (default: first order's symbol)
            
        Returns:
            List of ExecutionSimulationResult
        """
        results = []
        
        for order, bar in zip(orders, bars):
            if isinstance(bar, pd.Series):
                bar = bar.to_dict()
            
            timestamp = pd.Timestamp(bar.get("timestamp", pd.Timestamp.utcnow()))
            result = await self.simulate_execution(order, bar, timestamp=timestamp, symbol=symbol or order.symbol)
            results.append(result)
            
            # Update order age if not filled
            if result.status != OrderStatus.FILLED:
                order.update_age()
        
        return results

    def get_execution_metrics(self) -> dict[str, Any]:
        """Get execution metrics from tracker."""
        metrics = self.tracker.calculate_metrics()
        return {
            "total_orders": metrics.total_orders,
            "filled_orders": metrics.filled_orders,
            "cancelled_orders": metrics.cancelled_orders,
            "no_trades": metrics.no_trades,
            "fill_rate": metrics.fill_rate,
            "cancel_ratio": metrics.cancel_ratio,
            "no_trade_ratio": metrics.no_trade_ratio,
            "avg_wait_bars": metrics.avg_wait_bars,
            "avg_slippage_bps": metrics.avg_slippage_bps,
            "opportunity_cost": metrics.opportunity_cost,
            "orderbook_fallback_count": self.orderbook_fallback_count,
            "orderbook_warnings": [w.to_dict() for w in self.orderbook_warnings],
            "no_trade_events": [
                {
                    "timestamp": e.timestamp.isoformat(),
                    "symbol": e.symbol,
                    "side": e.side,
                    "reason": e.reason,
                    "fill_ratio": e.fill_ratio,
                }
                for e in metrics.no_trade_events
            ],
        }
    
    def reset_counters(self) -> None:
        """Reset orderbook fallback counters and warnings."""
        self.orderbook_warnings.clear()
        self.orderbook_fallback_count = 0

