"""Position management with automatic SL/TP recalculation after fills."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import pandas as pd

from app.backtesting.order_types import OrderResult, OrderSide, OrderStatus


class PositionSide(str, Enum):
    """Position side (long or short)."""

    LONG = "long"
    SHORT = "short"


@dataclass
class PositionConfig:
    """Configuration for position management."""

    risk_per_unit: float | None = None  # Risk per unit (price difference for SL)
    reward_per_unit: float | None = None  # Reward per unit (price difference for TP)
    risk_reward_ratio: float | None = None  # Reward/Risk ratio (e.g., 2.0 for 2:1)
    fixed_stop_loss: float | None = None  # Fixed stop loss price (if set, overrides risk_per_unit)
    fixed_take_profit: float | None = None  # Fixed take profit price (if set, overrides reward_per_unit)
    trailing_stop: bool = False  # Enable trailing stop
    trailing_stop_distance: float | None = None  # Distance for trailing stop
    trailing_sl: float | None = None  # Explicit trailing stop distance override
    breakeven_trigger: float | None = None  # Move SL to breakeven after this favorable move
    partial_take_profits: list[dict[str, float]] | None = None  # Optional partial TP definitions


@dataclass
class PositionState:
    """State of an open position."""

    symbol: str
    side: PositionSide
    size: float  # Total position size
    avg_entry: float  # Average entry price
    current_price: float  # Current market price
    stop_loss: float | None  # Current stop loss level
    take_profit: float | None  # Current take profit level
    risk_per_unit: float | None  # Risk per unit (for recalculation)
    reward_per_unit: float | None  # Reward per unit (for recalculation)
    unrealized_pnl: float = 0.0  # Unrealized P&L
    unrealized_pnl_pct: float = 0.0  # Unrealized P&L percentage
    opened_at: pd.Timestamp | None = None
    last_update: pd.Timestamp | None = None
    fills: list[dict[str, Any]] = field(default_factory=list)  # Fill history
    trailing_sl: float | None = None
    breakeven_trigger: float | None = None
    breakeven_active: bool = False
    partial_take_profits: list[dict[str, Any]] = field(default_factory=list)
    mae: float = 0.0
    mfe: float = 0.0


@dataclass
class PartialTakeProfitLevel:
    """Definition and execution state of a partial take profit level."""

    price: float
    qty_pct: float | None = None
    qty: float | None = None
    triggered: bool = False
    triggered_at: pd.Timestamp | None = None
    reference_size: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "price": self.price,
            "qty_pct": self.qty_pct,
            "qty": self.qty,
            "triggered": self.triggered,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "reference_size": self.reference_size,
        }


class Position:
    """
    Position manager with automatic SL/TP recalculation after fills.
    
    Maintains position state and automatically recalculates stop loss and take profit
    levels based on average entry price after each fill.
    """

    def __init__(
        self,
        symbol: str,
        side: PositionSide | str,
        *,
        config: PositionConfig | None = None,
        initial_fill_price: float | None = None,
        initial_qty: float | None = None,
        opened_at: pd.Timestamp | None = None,
    ) -> None:
        """
        Initialize position.
        
        Args:
            symbol: Trading symbol
            side: Position side ("long" or "short")
            config: Position configuration
            initial_fill_price: Optional initial fill price
            initial_qty: Optional initial quantity
            opened_at: Position open timestamp
        """
        self.symbol = symbol
        self.side = PositionSide(side) if isinstance(side, str) else side
        self.config = config or PositionConfig()
        self.opened_at = opened_at or pd.Timestamp.utcnow()
        
        # Initialize state
        self.size: float = 0.0
        self.avg_entry: float = 0.0
        self.current_price: float = 0.0
        self.stop_loss: float | None = None
        self.take_profit: float | None = None
        self.risk_per_unit: float | None = self.config.risk_per_unit
        self.reward_per_unit: float | None = self.config.reward_per_unit
        self.fills: list[dict[str, Any]] = []
        self.last_update: pd.Timestamp | None = None
        self.trailing_sl_distance: float | None = self.config.trailing_sl or self.config.trailing_stop_distance
        self.trailing_sl: float | None = None
        self.breakeven_trigger: float | None = self.config.breakeven_trigger
        self.breakeven_active = False
        self.partial_take_profits: list[PartialTakeProfitLevel] = []
        self.partial_execution_log: list[dict[str, Any]] = []
        self.max_favorable_price: float = 0.0
        self.max_adverse_price: float = 0.0
        self.mae: float = 0.0
        self.mfe: float = 0.0
        self.initial_size: float = 0.0

        # Apply initial fill if provided
        if initial_fill_price is not None and initial_qty is not None:
            self.apply_fill(initial_fill_price, initial_qty)
        
        # Calculate initial SL/TP if risk_reward_ratio provided
        if self.config.risk_reward_ratio is not None and self.risk_per_unit is not None:
            self.reward_per_unit = self.risk_per_unit * self.config.risk_reward_ratio
            self._recalculate_levels()

    def apply_fill(
        self,
        fill_price: float,
        qty: float,
        *,
        fill_timestamp: pd.Timestamp | None = None,
        order_id: str | None = None,
    ) -> None:
        """
        Apply a fill to the position and recalculate levels.
        
        For partial fills, calculates size-weighted average entry price and
        recalculates SL/TP based on new average entry.
        
        Args:
            fill_price: Fill price
            qty: Filled quantity
            fill_timestamp: Fill timestamp (default: now)
            order_id: Optional order ID
        """
        if qty <= 0:
            return
        
        fill_timestamp = fill_timestamp or pd.Timestamp.utcnow()
        is_new_position = self.size == 0

        # Calculate new average entry (size-weighted)
        if self.size > 0:
            # Existing position: weighted average
            total_cost = (self.avg_entry * self.size) + (fill_price * qty)
            total_size = self.size + qty
            self.avg_entry = total_cost / total_size
        else:
            # New position: use fill price
            self.avg_entry = fill_price
        
        # Update position size
        self.size += qty
        self.initial_size += qty

        if is_new_position:
            self.max_favorable_price = self.avg_entry
            self.max_adverse_price = self.avg_entry
            self.mae = 0.0
            self.mfe = 0.0

        # Record fill
        fill_record = {
            "timestamp": fill_timestamp.isoformat(),
            "price": fill_price,
            "qty": qty,
            "notional": fill_price * qty,
            "order_id": order_id,
        }
        self.fills.append(fill_record)
        self.last_update = fill_timestamp
        
        # Recalculate SL/TP levels
        self._recalculate_levels(rebuild_partials=True)
        
        # Update current price if not set
        if self.current_price == 0.0:
            self.current_price = fill_price

    def _recalculate_levels(self, *, rebuild_partials: bool = False) -> None:
        """Recalculate stop loss and take profit levels based on current average entry."""
        if self.avg_entry == 0.0:
            return
        
        # Use fixed levels if provided
        if self.config.fixed_stop_loss is not None:
            self.stop_loss = self.config.fixed_stop_loss
        elif self.risk_per_unit is not None:
            # Calculate stop loss based on risk per unit
            if self.side == PositionSide.LONG:
                self.stop_loss = self.avg_entry - self.risk_per_unit
            else:  # SHORT
                self.stop_loss = self.avg_entry + self.risk_per_unit
        else:
            self.stop_loss = None
        
        if self.config.fixed_take_profit is not None:
            self.take_profit = self.config.fixed_take_profit
        elif self.reward_per_unit is not None:
            # Calculate take profit based on reward per unit
            if self.side == PositionSide.LONG:
                self.take_profit = self.avg_entry + self.reward_per_unit
            else:  # SHORT
                self.take_profit = self.avg_entry - self.reward_per_unit
        else:
            self.take_profit = None

        if rebuild_partials:
            self._build_partial_take_profit_levels()

    def _build_partial_take_profit_levels(self) -> None:
        """Build partial take profit state from configuration."""
        self.partial_take_profits = []
        for level in self.config.partial_take_profits or []:
            price = level.get("price")
            if price is None:
                offset = level.get("offset")
                rr_multiple = level.get("rr_multiple")
                if rr_multiple is not None and self.reward_per_unit is not None:
                    offset = self.reward_per_unit * rr_multiple
                if offset is not None:
                    if self.side == PositionSide.LONG:
                        price = self.avg_entry + offset
                    else:
                        price = self.avg_entry - offset
            if price is None:
                continue
            self.partial_take_profits.append(
                PartialTakeProfitLevel(
                    price=float(price),
                    qty_pct=level.get("qty_pct"),
                    qty=level.get("qty"),
                    reference_size=self.size if self.size > 0 else None,
                )
            )

    def update_price(
        self, current_price: float, *, timestamp: pd.Timestamp | None = None
    ) -> list[dict[str, Any]]:
        """
        Update current market price and calculate unrealized P&L.
        
        Args:
            current_price: Current market price
        """
        self.current_price = current_price
        timestamp = timestamp or pd.Timestamp.utcnow()
        self.last_update = timestamp
        
        if self.size == 0 or self.avg_entry == 0.0:
            self.unrealized_pnl = 0.0
            self.unrealized_pnl_pct = 0.0
            return []
        
        # Calculate unrealized P&L
        price_diff = current_price - self.avg_entry
        
        if self.side == PositionSide.LONG:
            self.unrealized_pnl = price_diff * self.size
        else:  # SHORT
            self.unrealized_pnl = -price_diff * self.size
        
        # Calculate percentage
        if self.avg_entry > 0:
            self.unrealized_pnl_pct = (self.unrealized_pnl / (self.avg_entry * self.size)) * 100.0
        else:
            self.unrealized_pnl_pct = 0.0

        self._update_extrema(current_price)
        breakeven_triggered = self._maybe_move_to_breakeven(current_price)
        self._update_trailing_stop(current_price, skip_this_bar=breakeven_triggered)
        partial_events = self._process_partial_take_profits(current_price, timestamp)

        return partial_events

    def _update_extrema(self, current_price: float) -> None:
        """Update MAE/MFE tracking based on the latest price."""
        if self.max_favorable_price == 0.0:
            self.max_favorable_price = self.avg_entry
            self.max_adverse_price = self.avg_entry

        if self.side == PositionSide.LONG:
            self.max_favorable_price = max(self.max_favorable_price, current_price)
            self.max_adverse_price = min(self.max_adverse_price, current_price)
            self.mfe = max(self.mfe, self.max_favorable_price - self.avg_entry)
            self.mae = max(self.mae, self.avg_entry - self.max_adverse_price)
        else:
            self.max_favorable_price = min(self.max_favorable_price, current_price)
            self.max_adverse_price = max(self.max_adverse_price, current_price)
            self.mfe = max(self.mfe, self.avg_entry - self.max_favorable_price)
            self.mae = max(self.mae, self.max_adverse_price - self.avg_entry)

    def _maybe_move_to_breakeven(self, current_price: float) -> bool:
        """Move stop loss to breakeven once the trigger distance is reached."""
        if self.breakeven_active or self.breakeven_trigger is None:
            return False
        move_distance = current_price - self.avg_entry if self.side == PositionSide.LONG else self.avg_entry - current_price
        if move_distance >= self.breakeven_trigger:
            self.stop_loss = self.avg_entry
            self.breakeven_active = True
            return True

        return False

    def _update_trailing_stop(self, current_price: float, *, skip_this_bar: bool = False) -> None:
        """Update trailing stop level based on MFE and configured distance."""
        if not self.config.trailing_stop or self.trailing_sl_distance is None:
            return
        if skip_this_bar:
            return
        if self.breakeven_trigger is not None and not self.breakeven_active:
            return

        if self.side == PositionSide.LONG:
            candidate = self.max_favorable_price - self.trailing_sl_distance
            if candidate > (self.stop_loss or float("-inf")):
                self.stop_loss = candidate
                self.trailing_sl = candidate
        else:
            candidate = self.max_favorable_price + self.trailing_sl_distance
            if self.stop_loss is None or candidate < self.stop_loss:
                self.stop_loss = candidate
                self.trailing_sl = candidate

    def _process_partial_take_profits(
        self, current_price: float, timestamp: pd.Timestamp
    ) -> list[dict[str, Any]]:
        """Trigger partial take profits when price reaches configured levels."""
        events: list[dict[str, Any]] = []
        for level in self.partial_take_profits:
            if level.triggered:
                continue
            should_trigger = False
            if self.side == PositionSide.LONG and current_price >= level.price:
                should_trigger = True
            elif self.side == PositionSide.SHORT and current_price <= level.price:
                should_trigger = True

            if not should_trigger:
                continue

            qty = level.qty or 0.0
            qty_base = level.reference_size or self.size
            if qty == 0.0 and level.qty_pct is not None:
                qty = max(qty_base * level.qty_pct, 0.0)
            qty = min(qty, self.size)

            if qty <= 0:
                level.triggered = True
                level.triggered_at = timestamp
                continue

            close_result = self.apply_partial_close(level.price, qty, close_timestamp=timestamp)
            close_result["partial_take_profit"] = True
            close_result["target_price"] = level.price
            self.partial_execution_log.append(close_result)
            events.append(close_result)
            level.triggered = True
            level.triggered_at = timestamp

        return events

    def update_levels_from_config(self, config: PositionConfig) -> None:
        """
        Update position levels from new configuration.
        
        Useful for updating risk/reward parameters during position lifetime.
        
        Args:
            config: New position configuration
        """
        self.config = config
        
        # Update risk/reward per unit if provided
        if config.risk_per_unit is not None:
            self.risk_per_unit = config.risk_per_unit
        if config.reward_per_unit is not None:
            self.reward_per_unit = config.reward_per_unit
        
        # Recalculate reward_per_unit from ratio if needed
        if config.risk_reward_ratio is not None and self.risk_per_unit is not None:
            self.reward_per_unit = self.risk_per_unit * config.risk_reward_ratio
        
        # Recalculate levels
        self.trailing_sl_distance = config.trailing_sl or config.trailing_stop_distance
        self.breakeven_trigger = config.breakeven_trigger

        self._recalculate_levels(rebuild_partials=True)

    def check_exit_conditions(self) -> dict[str, Any]:
        """
        Check if position should be closed based on SL/TP levels.
        
        Returns:
            Dict with exit information or None if no exit triggered
        """
        if self.size == 0 or self.current_price == 0.0:
            return {"exit_triggered": False}
        
        exit_price = None
        exit_reason = None
        
        # Check stop loss
        if self.stop_loss is not None:
            if self.side == PositionSide.LONG:
                if self.current_price <= self.stop_loss:
                    exit_price = self.stop_loss
                    exit_reason = "stop_loss"
            else:  # SHORT
                if self.current_price >= self.stop_loss:
                    exit_price = self.stop_loss
                    exit_reason = "stop_loss"
        
        # Check take profit
        if self.take_profit is not None and not exit_reason:
            if self.side == PositionSide.LONG:
                if self.current_price >= self.take_profit:
                    exit_price = self.take_profit
                    exit_reason = "take_profit"
            else:  # SHORT
                if self.current_price <= self.take_profit:
                    exit_price = self.take_profit
                    exit_reason = "take_profit"
        
        if exit_reason:
            # Calculate realized P&L
            price_diff = exit_price - self.avg_entry
            
            if self.side == PositionSide.LONG:
                realized_pnl = price_diff * self.size
            else:  # SHORT
                realized_pnl = -price_diff * self.size
            
            realized_pnl_pct = (realized_pnl / (self.avg_entry * self.size)) * 100.0 if self.avg_entry > 0 else 0.0
            
            return {
                "exit_triggered": True,
                "exit_reason": exit_reason,
                "exit_price": exit_price,
                "realized_pnl": realized_pnl,
                "realized_pnl_pct": realized_pnl_pct,
                "entry_price": self.avg_entry,
                "position_size": self.size,
            }
        
        return {"exit_triggered": False}

    def apply_partial_close(
        self,
        close_price: float,
        qty: float,
        *,
        close_timestamp: pd.Timestamp | None = None,
    ) -> dict[str, Any]:
        """
        Apply partial position close.
        
        Reduces position size and calculates realized P&L for closed portion.
        SL/TP levels remain based on remaining position's average entry.
        
        Args:
            close_price: Close price
            qty: Quantity to close
            close_timestamp: Close timestamp
            
        Returns:
            Dict with realized P&L information
        """
        if qty <= 0 or qty > self.size:
            return {"error": "Invalid close quantity"}
        
        close_timestamp = close_timestamp or pd.Timestamp.utcnow()
        
        # Calculate realized P&L for closed portion
        price_diff = close_price - self.avg_entry
        
        if self.side == PositionSide.LONG:
            realized_pnl = price_diff * qty
        else:  # SHORT
            realized_pnl = -price_diff * qty
        
        realized_pnl_pct = (realized_pnl / (self.avg_entry * qty)) * 100.0 if self.avg_entry > 0 else 0.0
        
        # Update position size
        self.size -= qty
        
        # If position fully closed, reset average entry
        if self.size == 0:
            self.avg_entry = 0.0
            self.stop_loss = None
            self.take_profit = None
            self.partial_take_profits = []
            self.initial_size = 0.0
            self.breakeven_active = False
            self.trailing_sl = None
        
        # Note: SL/TP levels remain based on original avg_entry for remaining position
        # If you want to recalculate for remaining position, call _recalculate_levels()
        
        self.last_update = close_timestamp
        
        return {
            "closed_qty": qty,
            "close_price": close_price,
            "realized_pnl": realized_pnl,
            "realized_pnl_pct": realized_pnl_pct,
            "remaining_size": self.size,
            "remaining_avg_entry": self.avg_entry,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert position to dictionary."""
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "size": self.size,
            "avg_entry": self.avg_entry,
            "current_price": self.current_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "risk_per_unit": self.risk_per_unit,
            "reward_per_unit": self.reward_per_unit,
            "unrealized_pnl": self.unrealized_pnl,
            "unrealized_pnl_pct": self.unrealized_pnl_pct,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "num_fills": len(self.fills),
            "trailing_sl": self.trailing_sl,
            "breakeven_trigger": self.breakeven_trigger,
            "breakeven_active": self.breakeven_active,
            "partial_take_profits": [level.to_dict() for level in self.partial_take_profits],
            "mae": self.mae,
            "mfe": self.mfe,
        }

    def get_state(self) -> PositionState:
        """Get current position state."""
        return PositionState(
            symbol=self.symbol,
            side=self.side,
            size=self.size,
            avg_entry=self.avg_entry,
            current_price=self.current_price,
            stop_loss=self.stop_loss,
            take_profit=self.take_profit,
            risk_per_unit=self.risk_per_unit,
            reward_per_unit=self.reward_per_unit,
            unrealized_pnl=self.unrealized_pnl,
            unrealized_pnl_pct=self.unrealized_pnl_pct,
            opened_at=self.opened_at,
            last_update=self.last_update,
            fills=self.fills.copy(),
            trailing_sl=self.trailing_sl,
            breakeven_trigger=self.breakeven_trigger,
            breakeven_active=self.breakeven_active,
            partial_take_profits=[level.to_dict() for level in self.partial_take_profits],
            mae=self.mae,
            mfe=self.mfe,
        )

    def get_trade_analytics(self) -> dict[str, float]:
        """Return MAE/MFE metrics for downstream analytics."""
        base = abs(self.avg_entry) if self.avg_entry else 0.0
        mae_pct = (self.mae / base) * 100.0 if base else 0.0
        mfe_pct = (self.mfe / base) * 100.0 if base else 0.0
        return {"mae": self.mae, "mfe": self.mfe, "mae_pct": mae_pct, "mfe_pct": mfe_pct}


class PositionManager:
    """Manager for multiple positions."""

    def __init__(self) -> None:
        """Initialize position manager."""
        self.positions: dict[str, Position] = {}  # key: symbol

    def get_position(self, symbol: str) -> Position | None:
        """Get position for symbol."""
        return self.positions.get(symbol)

    def open_position(
        self,
        symbol: str,
        side: PositionSide | str,
        fill_price: float,
        qty: float,
        *,
        config: PositionConfig | None = None,
        opened_at: pd.Timestamp | None = None,
    ) -> Position:
        """
        Open a new position or add to existing position.
        
        Args:
            symbol: Trading symbol
            side: Position side
            fill_price: Entry fill price
            qty: Quantity
            config: Position configuration
            opened_at: Open timestamp
            
        Returns:
            Position object
        """
        existing = self.positions.get(symbol)
        
        if existing:
            # Add to existing position
            existing.apply_fill(fill_price, qty, fill_timestamp=opened_at)
            return existing
        else:
            # Create new position
            position = Position(
                symbol=symbol,
                side=side,
                config=config,
                initial_fill_price=fill_price,
                initial_qty=qty,
                opened_at=opened_at,
            )
            self.positions[symbol] = position
            return position

    def close_position(
        self,
        symbol: str,
        close_price: float,
        *,
        partial_qty: float | None = None,
        close_timestamp: pd.Timestamp | None = None,
    ) -> dict[str, Any] | None:
        """
        Close position (full or partial).
        
        Args:
            symbol: Trading symbol
            close_price: Close price
            partial_qty: Optional partial close quantity (if None, closes all)
            close_timestamp: Close timestamp
            
        Returns:
            Dict with close details or None if position not found
        """
        position = self.positions.get(symbol)
        if not position:
            return None
        
        if partial_qty is None:
            # Close entire position
            partial_qty = position.size
        
        result = position.apply_partial_close(close_price, partial_qty, close_timestamp=close_timestamp)
        
        # Remove position if fully closed
        if position.size == 0:
            del self.positions[symbol]
        
        return result

    def update_prices(self, prices: dict[str, float]) -> None:
        """
        Update prices for all positions.
        
        Args:
            prices: Dict of symbol -> current_price
        """
        for symbol, price in prices.items():
            position = self.positions.get(symbol)
            if position:
                position.update_price(price)

    def check_all_exits(self) -> list[dict[str, Any]]:
        """
        Check exit conditions for all positions.
        
        Returns:
            List of exit information for positions that should be closed
        """
        exits = []
        for symbol, position in list(self.positions.items()):
            exit_info = position.check_exit_conditions()
            if exit_info.get("exit_triggered"):
                exit_info["symbol"] = symbol
                exits.append(exit_info)
        return exits



