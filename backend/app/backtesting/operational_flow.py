"""Operational flow for ingestion, preprocessing, simulation, and reporting."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from app.backtesting.execution_simulator import ExecutionSimulator, ExecutionSimulationResult
from app.backtesting.position import Position, PositionConfig, PositionSide
from app.backtesting.stop_rebalancer import StopRebalancer
from app.backtesting.tracking_error import calculate_tracking_error
from app.data.orderbook import OrderBookRepository
from app.data.preprocessing import batch_preprocess_snapshots, preprocess_orderbook_snapshot


@dataclass
class OperationalFlowResult:
    """Result of complete operational flow."""

    # Execution results
    fills: list[ExecutionSimulationResult]
    
    # Stop rebalancing
    rebalance_events: list[dict[str, Any]]
    
    # Metrics
    execution_metrics: dict[str, Any]
    tracking_error: dict[str, Any] | None
    
    # Processed data
    preprocessed_snapshots: pd.DataFrame | None


class OperationalFlow:
    """
    Complete operational flow:
    1. Ingestion: Store candles and order books synchronized
    2. Preprocessing: Derive spread, imbalance, effective depth
    3. Simulation: ExecutionSimulator consumes order books for fills, slippage, failures
    4. Stop rebalancing: Each fill adjusts levels and documents changes
    5. Reporting: Expose fill rate, tracking error, realized slippage, and comparison vs theoretical
    """

    def __init__(
        self,
        orderbook_repo: OrderBookRepository | None = None,
        execution_simulator: ExecutionSimulator | None = None,
    ) -> None:
        """
        Initialize operational flow.
        
        Args:
            orderbook_repo: Order book repository (assumes ingestion already done)
            execution_simulator: Execution simulator (optional, creates default if None)
        """
        self.orderbook_repo = orderbook_repo or OrderBookRepository()
        self.execution_simulator = execution_simulator or ExecutionSimulator(
            orderbook_repo=self.orderbook_repo
        )

    async def process_order_with_rebalancing(
        self,
        order: Any,  # BaseOrder or compatible
        bar: dict[str, Any] | pd.Series,
        position: Position,
        *,
        timestamp: pd.Timestamp | None = None,
        symbol: str | None = None,
    ) -> tuple[ExecutionSimulationResult, dict[str, Any] | None]:
        """
        Process order through complete flow: execution → stop rebalancing.
        
        Args:
            order: Order to execute
            bar: Current bar data
            position: Position to update
            timestamp: Timestamp for order book lookup
            symbol: Trading symbol
            
        Returns:
            Tuple of (ExecutionSimulationResult, StopRebalanceEvent dict or None)
        """
        # Step 1: Simulate execution
        execution_result = await self.execution_simulator.simulate_execution(
            order, bar, timestamp=timestamp, symbol=symbol
        )
        
        # Step 2: Apply fill and rebalance stops if filled
        rebalance_event = None
        if execution_result.filled_qty > 0:
            rebalancer = StopRebalancer(position)
            rebalance_event = rebalancer.apply_fill_and_rebalance(
                execution_result.avg_fill_price,
                execution_result.filled_qty,
                fill_timestamp=timestamp,
                order_id=getattr(order, "order_id", None),
            )
            rebalance_event = rebalance_event.__dict__
        
        return execution_result, rebalance_event

    async def preprocess_orderbook_for_order(
        self,
        symbol: str,
        timestamp: pd.Timestamp,
        notional: float,
        side: str = "buy",
    ) -> dict[str, Any]:
        """
        Preprocess order book snapshot for an order.
        
        Args:
            symbol: Trading symbol
            timestamp: Timestamp for snapshot
            notional: Order notional size
            side: Order side ("buy" or "sell")
            
        Returns:
            Preprocessed metrics dict
        """
        snapshot = await self.orderbook_repo.get_snapshot(symbol, timestamp, tolerance_seconds=30)
        
        if not snapshot:
            return {
                "timestamp": timestamp.isoformat(),
                "snapshot_available": False,
            }
        
        return preprocess_orderbook_snapshot(snapshot, notional=notional, side=side)

    async def run_complete_flow(
        self,
        orders: list[Any],  # List of BaseOrder or compatible
        bars: list[dict[str, Any] | pd.Series],
        position: Position,
        *,
        symbol: str | None = None,
        theoretical_equity: list[float] | None = None,
        realistic_equity: list[float] | None = None,
    ) -> OperationalFlowResult:
        """
        Run complete operational flow for a sequence of orders.
        
        Args:
            orders: List of orders to execute
            bars: List of bar data (should match orders)
            position: Position to manage
            symbol: Trading symbol
            theoretical_equity: Theoretical equity curve (for tracking error)
            realistic_equity: Realistic equity curve (for tracking error)
            
        Returns:
            OperationalFlowResult with all results
        """
        fills = []
        rebalance_events = []
        
        # Process each order
        for order, bar in zip(orders, bars):
            if isinstance(bar, pd.Series):
                bar = bar.to_dict()
            
            timestamp = pd.Timestamp(bar.get("timestamp", pd.Timestamp.utcnow()))
            
            # Execute and rebalance
            execution_result, rebalance_event = await self.process_order_with_rebalancing(
                order, bar, position, timestamp=timestamp, symbol=symbol
            )
            
            fills.append(execution_result)
            if rebalance_event:
                rebalance_events.append(rebalance_event)
        
        # Get execution metrics
        execution_metrics = self.execution_simulator.get_execution_metrics()
        
        # Calculate tracking error if curves provided
        tracking_error = None
        if theoretical_equity and realistic_equity:
            tracking_error = calculate_tracking_error(theoretical_equity, realistic_equity)
        
        # Get preprocessed snapshots if available
        preprocessed_snapshots = None
        if fills:
            # Extract snapshots from execution results
            snapshots = [f.order_book_snapshot for f in fills if f.order_book_snapshot]
            if snapshots:
                preprocessed_snapshots = batch_preprocess_snapshots(snapshots)
        
        return OperationalFlowResult(
            fills=fills,
            rebalance_events=rebalance_events,
            execution_metrics=execution_metrics,
            tracking_error=tracking_error,
            preprocessed_snapshots=preprocessed_snapshots,
        )


def generate_operational_report(result: OperationalFlowResult) -> dict[str, Any]:
    """
    Generate comprehensive operational report.
    
    Exposes:
    - Fill rate and execution statistics
    - Tracking error metrics
    - Realized slippage distribution
    - Comparison vs theoretical
    - Stop rebalancing activity
    """
    report = {
        "execution": result.execution_metrics,
        "stop_rebalancing": {
            "total_rebalances": len(result.rebalance_events),
            "rebalance_history": result.rebalance_events[:10],  # First 10
        },
    }
    
    # Slippage statistics from fills
    if result.fills:
        slippages = [f.slippage_bps for f in result.fills if f.filled_qty > 0]
        fill_ratios = [f.fill_ratio for f in result.fills]
        
        if slippages:
            import numpy as np
            
            report["realized_slippage"] = {
                "avg_bps": float(np.mean(slippages)),
                "median_bps": float(np.median(slippages)),
                "p95_bps": float(np.percentile(slippages, 95)),
                "max_bps": float(np.max(slippages)),
                "std_bps": float(np.std(slippages)),
            }
        
        if fill_ratios:
            import numpy as np
            
            report["fill_ratios"] = {
                "avg": float(np.mean(fill_ratios)),
                "median": float(np.median(fill_ratios)),
                "min": float(np.min(fill_ratios)),
                "p95": float(np.percentile(fill_ratios, 95)),
                "complete_fills": sum(1 for r in fill_ratios if r >= 1.0),
                "partial_fills": sum(1 for r in fill_ratios if 0 < r < 1.0),
                "failed_fills": sum(1 for r in fill_ratios if r == 0.0),
            }
    
    # Tracking error
    if result.tracking_error:
        report["tracking_error"] = result.tracking_error
    
    # Preprocessing summary
    if result.preprocessed_snapshots is not None and not result.preprocessed_snapshots.empty:
        df = result.preprocessed_snapshots
        
        if "spread_bps" in df.columns:
            report["orderbook_metrics"] = {
                "avg_spread_bps": float(df["spread_bps"].mean()),
                "avg_imbalance_pct": float(df["imbalance_pct"].mean()) if "imbalance_pct" in df.columns else 0.0,
            }
    
    return report



