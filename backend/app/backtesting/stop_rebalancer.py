"""Stop loss and take profit rebalancing system that adjusts levels after each fill."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.backtesting.position import Position, PositionConfig, PositionSide


@dataclass
class StopRebalanceEvent:
    """Event documenting stop level changes after a fill."""

    timestamp: pd.Timestamp
    fill_price: float
    fill_qty: float
    old_stop_loss: float | None
    new_stop_loss: float | None
    old_take_profit: float | None
    new_take_profit: float | None
    old_avg_entry: float
    new_avg_entry: float
    reason: str = "fill_rebalance"  # "fill_rebalance", "manual", "regime_change"


class StopRebalancer:
    """
    System for rebalancing stop loss and take profit levels after each fill.
    
    Automatically recalculates SL/TP based on new average entry price after partial fills,
    and documents all level changes for auditing and analysis.
    """

    def __init__(self, position: Position) -> None:
        """
        Initialize stop rebalancer for a position.
        
        Args:
            position: Position to manage
        """
        self.position = position
        self.rebalance_history: list[StopRebalanceEvent] = []

    def apply_fill_and_rebalance(
        self,
        fill_price: float,
        qty: float,
        *,
        fill_timestamp: pd.Timestamp | None = None,
        order_id: str | None = None,
        reason: str = "fill_rebalance",
    ) -> StopRebalanceEvent:
        """
        Apply fill to position and rebalance stop levels.
        
        Args:
            fill_price: Fill price
            qty: Fill quantity
            fill_timestamp: Fill timestamp
            order_id: Optional order ID
            reason: Reason for rebalance
            
        Returns:
            StopRebalanceEvent documenting the changes
        """
        fill_timestamp = fill_timestamp or pd.Timestamp.utcnow()
        
        # Record old levels
        old_stop_loss = self.position.stop_loss
        old_take_profit = self.position.take_profit
        old_avg_entry = self.position.avg_entry
        
        # Apply fill (this will recalculate levels)
        self.position.apply_fill(fill_price, qty, fill_timestamp=fill_timestamp, order_id=order_id)
        
        # Record new levels
        new_stop_loss = self.position.stop_loss
        new_take_profit = self.position.take_profit
        new_avg_entry = self.position.avg_entry
        
        # Create rebalance event
        event = StopRebalanceEvent(
            timestamp=fill_timestamp,
            fill_price=fill_price,
            fill_qty=qty,
            old_stop_loss=old_stop_loss,
            new_stop_loss=new_stop_loss,
            old_take_profit=old_take_profit,
            new_take_profit=new_take_profit,
            old_avg_entry=old_avg_entry,
            new_avg_entry=new_avg_entry,
            reason=reason,
        )
        
        self.rebalance_history.append(event)
        return event

    def manual_rebalance(
        self,
        new_stop_loss: float | None = None,
        new_take_profit: float | None = None,
        *,
        timestamp: pd.Timestamp | None = None,
        reason: str = "manual",
    ) -> StopRebalanceEvent:
        """
        Manually rebalance stop levels.
        
        Args:
            new_stop_loss: New stop loss level (None to keep current)
            new_take_profit: New take profit level (None to keep current)
            timestamp: Timestamp for rebalance
            reason: Reason for manual rebalance
            
        Returns:
            StopRebalanceEvent documenting the changes
        """
        timestamp = timestamp or pd.Timestamp.utcnow()
        
        # Record old levels
        old_stop_loss = self.position.stop_loss
        old_take_profit = self.position.take_profit
        old_avg_entry = self.position.avg_entry
        
        # Update position levels directly
        if new_stop_loss is not None:
            self.position.stop_loss = new_stop_loss
        if new_take_profit is not None:
            self.position.take_profit = new_take_profit
        
        # Record new levels (after update)
        new_stop_loss = self.position.stop_loss if new_stop_loss is None else new_stop_loss
        new_take_profit = self.position.take_profit if new_take_profit is None else new_take_profit
        
        # Create rebalance event
        event = StopRebalanceEvent(
            timestamp=timestamp,
            fill_price=self.position.avg_entry,
            fill_qty=0.0,
            old_stop_loss=old_stop_loss,
            new_stop_loss=new_stop_loss,
            old_take_profit=old_take_profit,
            new_take_profit=new_take_profit,
            old_avg_entry=old_avg_entry,
            new_avg_entry=self.position.avg_entry,
            reason=reason,
        )
        
        self.rebalance_history.append(event)
        return event

    def regime_change_rebalance(
        self,
        new_config: PositionConfig,
        *,
        timestamp: pd.Timestamp | None = None,
    ) -> StopRebalanceEvent:
        """
        Rebalance stop levels due to regime change.
        
        Args:
            new_config: New position configuration for regime
            timestamp: Timestamp for rebalance
            
        Returns:
            StopRebalanceEvent documenting the changes
        """
        timestamp = timestamp or pd.Timestamp.utcnow()
        
        # Record old levels
        old_stop_loss = self.position.stop_loss
        old_take_profit = self.position.take_profit
        old_avg_entry = self.position.avg_entry
        
        # Update configuration
        old_config = self.position.config
        self.position.config = new_config
        
        # Recalculate levels based on new config
        if new_config.risk_per_unit is not None:
            self.position.risk_per_unit = new_config.risk_per_unit
        if new_config.reward_per_unit is not None:
            self.position.reward_per_unit = new_config.reward_per_unit
        if new_config.risk_reward_ratio is not None and self.position.risk_per_unit is not None:
            self.position.reward_per_unit = self.position.risk_per_unit * new_config.risk_reward_ratio
        
        # Recalculate levels
        self.position._recalculate_levels()
        
        # Create rebalance event
        event = StopRebalanceEvent(
            timestamp=timestamp,
            fill_price=self.position.avg_entry,
            fill_qty=0.0,
            old_stop_loss=old_stop_loss,
            new_stop_loss=self.position.stop_loss,
            old_take_profit=old_take_profit,
            new_take_profit=self.position.take_profit,
            old_avg_entry=old_avg_entry,
            new_avg_entry=self.position.avg_entry,
            reason="regime_change",
        )
        
        self.rebalance_history.append(event)
        return event

    def get_rebalance_history(self) -> list[dict[str, Any]]:
        """Get formatted rebalance history."""
        return [
            {
                "timestamp": e.timestamp.isoformat(),
                "fill_price": e.fill_price,
                "fill_qty": e.fill_qty,
                "old_stop_loss": e.old_stop_loss,
                "new_stop_loss": e.new_stop_loss,
                "old_take_profit": e.old_take_profit,
                "new_take_profit": e.new_take_profit,
                "old_avg_entry": e.old_avg_entry,
                "new_avg_entry": e.new_avg_entry,
                "reason": e.reason,
            }
            for e in self.rebalance_history
        ]

