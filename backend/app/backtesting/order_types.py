"""Order type hierarchy with fill simulation logic."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import pandas as pd

from app.data.fill_model import FillModel, FillSimulator
from app.data.orderbook import OrderBookSnapshot


class OrderStatus(str, Enum):
    """Order execution status."""

    PENDING = "pending"
    ACTIVE = "active"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class OrderSide(str, Enum):
    """Order side (buy or sell)."""

    BUY = "buy"
    SELL = "sell"


@dataclass
class OrderConfig:
    """Configuration for order execution."""

    max_wait_bars: int = 10  # Maximum bars to wait before cancellation
    stop_trigger_type: str = "market"  # "market" or "limit" for stop orders
    limit_price_tolerance: float = 0.001  # 0.1% tolerance for limit order matching
    fill_partial: bool = True  # Allow partial fills


@dataclass
class OrderResult:
    """Result of order execution attempt."""

    filled_qty: float
    avg_price: float
    filled_notional: float
    slippage_pct: float
    slippage_bps: float
    status: OrderStatus
    partial_fills: list[dict[str, Any]] = field(default_factory=list)


class BaseOrder(ABC):
    """Base class for all order types."""

    def __init__(
        self,
        symbol: str,
        side: OrderSide | str,
        qty: float,
        *,
        order_id: str | None = None,
        timestamp: pd.Timestamp | None = None,
        config: OrderConfig | None = None,
        fill_model: FillModel | None = None,
    ) -> None:
        """
        Initialize base order.
        
        Args:
            symbol: Trading symbol
            side: Order side ("buy" or "sell")
            qty: Order quantity
            order_id: Optional order ID
            timestamp: Order creation timestamp
            config: Order configuration
            fill_model: Optional fill model for slippage estimation
        """
        self.symbol = symbol
        self.side = OrderSide(side) if isinstance(side, str) else side
        self.qty = qty
        self.order_id = order_id or f"order_{pd.Timestamp.now().value}"
        self.timestamp = timestamp or pd.Timestamp.utcnow()
        self.config = config or OrderConfig()
        self.fill_model = fill_model or FillModel()
        
        # Execution state
        self.filled: float = 0.0
        self.status: OrderStatus = OrderStatus.PENDING
        self.age: int = 0  # Number of bars since creation
        self.avg_fill_price: float = 0.0
        self.execution_history: list[dict[str, Any]] = []

    @property
    def remaining_qty(self) -> float:
        """Get remaining unfilled quantity."""
        return self.qty - self.filled

    @property
    def fill_ratio(self) -> float:
        """Get fill ratio (0.0 to 1.0)."""
        return self.filled / self.qty if self.qty > 0 else 0.0

    @property
    def is_complete(self) -> bool:
        """Check if order is completely filled."""
        return self.filled >= self.qty

    def update_age(self) -> None:
        """Increment order age (called each bar)."""
        self.age += 1

    @abstractmethod
    def try_fill(
        self,
        bar: dict[str, Any] | pd.Series,
        book: OrderBookSnapshot | None = None,
    ) -> OrderResult:
        """
        Attempt to fill order against current bar and order book.
        
        Args:
            bar: Current bar data (OHLCV)
            book: Optional order book snapshot
            
        Returns:
            OrderResult with execution details
        """
        pass

    def match_against_book(
        self,
        book: OrderBookSnapshot,
        target_qty: float | None = None,
    ) -> tuple[float, float]:
        """
        Match order against order book levels.
        
        Args:
            book: Order book snapshot
            target_qty: Quantity to match (default: remaining_qty)
            
        Returns:
            (executed_qty, avg_price)
        """
        if target_qty is None:
            target_qty = self.remaining_qty
        
        if target_qty <= 0:
            return (0.0, 0.0)
        
        executed_qty = 0.0
        total_cost = 0.0
        
        if self.side == OrderSide.BUY:
            # Match against asks (ascending price)
            for price, level_qty in book.asks:
                if executed_qty >= target_qty:
                    break
                
                fill_qty = min(target_qty - executed_qty, level_qty)
                executed_qty += fill_qty
                total_cost += price * fill_qty
        else:  # SELL
            # Match against bids (descending price)
            for price, level_qty in book.bids:
                if executed_qty >= target_qty:
                    break
                
                fill_qty = min(target_qty - executed_qty, level_qty)
                executed_qty += fill_qty
                total_cost += price * fill_qty
        
        avg_price = total_cost / executed_qty if executed_qty > 0 else 0.0
        return (executed_qty, avg_price)

    def cancel(self, reason: str = "timeout") -> None:
        """Cancel the order."""
        self.status = OrderStatus.CANCELLED

    def to_dict(self) -> dict[str, Any]:
        """Convert order to dictionary."""
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "qty": self.qty,
            "filled": self.filled,
            "remaining_qty": self.remaining_qty,
            "status": self.status.value,
            "age": self.age,
            "avg_fill_price": self.avg_fill_price,
            "fill_ratio": self.fill_ratio,
            "timestamp": self.timestamp.isoformat(),
            "order_type": self.__class__.__name__,
        }


class MarketOrder(BaseOrder):
    """Market order - always executes at market price with slippage."""

    def try_fill(
        self,
        bar: dict[str, Any] | pd.Series,
        book: OrderBookSnapshot | None = None,
    ) -> OrderResult:
        """
        Execute market order - always fills with slippage.
        
        If order book available, uses it for precise execution.
        Otherwise, uses bar OHLC with slippage estimation.
        """
        target_qty = self.remaining_qty
        if target_qty <= 0:
            return OrderResult(
                filled_qty=0.0,
                avg_price=0.0,
                filled_notional=0.0,
                slippage_pct=0.0,
                slippage_bps=0.0,
                status=self.status,
            )
        
        # Use order book if available for precise execution
        if book:
            executed_qty, avg_price = self.match_against_book(book, target_qty)
            
            # Calculate slippage against mid price
            mid_price = book.mid_price or avg_price
            reference_price = book.best_ask if self.side == OrderSide.BUY else book.best_bid
            
            if reference_price and reference_price > 0:
                slippage_pct = abs((avg_price - reference_price) / reference_price)
            else:
                slippage_pct = 0.0
            
            # Estimate volatility from spread
            vol_est = book.spread_pct / 100.0 if book.spread_pct else 0.02
            expected_slippage = self.fill_model.expected_slippage(
                self.side.value,
                avg_price * executed_qty,
                book,
                vol_est,
            )
            
            # Use actual slippage or expected, whichever is higher
            slippage_pct = max(slippage_pct, expected_slippage)
        else:
            # Fallback to bar-based execution
            if isinstance(bar, pd.Series):
                bar = bar.to_dict()
            
            # Execute at VWAP approximation (mid of high/low for side)
            if self.side == OrderSide.BUY:
                # Buy at ask (approximate with high)
                avg_price = float(bar.get("high", bar.get("close", 0.0)))
            else:
                # Sell at bid (approximate with low)
                avg_price = float(bar.get("low", bar.get("close", 0.0)))
            
            executed_qty = target_qty
            
            # Estimate slippage (default 0.1% for market orders)
            slippage_pct = 0.001
        
        # Update order state
        self.filled += executed_qty
        self.avg_fill_price = (
            (self.avg_fill_price * (self.filled - executed_qty) + avg_price * executed_qty) / self.filled
            if self.filled > 0
            else avg_price
        )
        
        # Record execution
        execution_record = {
            "timestamp": bar.get("timestamp", pd.Timestamp.utcnow()).isoformat() if isinstance(bar, dict) else pd.Timestamp.utcnow().isoformat(),
            "qty": executed_qty,
            "price": avg_price,
            "notional": avg_price * executed_qty,
        }
        self.execution_history.append(execution_record)
        
        # Update status
        if self.is_complete:
            self.status = OrderStatus.FILLED
        elif self.filled > 0:
            self.status = OrderStatus.PARTIALLY_FILLED
        else:
            self.status = OrderStatus.ACTIVE
        
        filled_notional = avg_price * executed_qty
        slippage_bps = slippage_pct * 10000
        
        return OrderResult(
            filled_qty=executed_qty,
            avg_price=avg_price,
            filled_notional=filled_notional,
            slippage_pct=slippage_pct,
            slippage_bps=slippage_bps,
            status=self.status,
            partial_fills=[execution_record],
        )


class LimitOrder(BaseOrder):
    """Limit order - executes only at limit price or better."""

    def __init__(
        self,
        symbol: str,
        side: OrderSide | str,
        qty: float,
        limit_price: float,
        *,
        order_id: str | None = None,
        timestamp: pd.Timestamp | None = None,
        config: OrderConfig | None = None,
        fill_model: FillModel | None = None,
    ) -> None:
        """
        Initialize limit order.
        
        Args:
            limit_price: Limit price (max for buy, min for sell)
        """
        super().__init__(symbol, side, qty, order_id=order_id, timestamp=timestamp, config=config, fill_model=fill_model)
        self.limit_price = limit_price
        self.status = OrderStatus.ACTIVE

    def try_fill(
        self,
        bar: dict[str, Any] | pd.Series,
        book: OrderBookSnapshot | None = None,
    ) -> OrderResult:
        """
        Attempt to fill limit order.
        
        Fills if:
        - Buy: market price <= limit_price
        - Sell: market price >= limit_price
        
        Cancels if max_wait_bars exceeded and not fully filled.
        """
        # Check if order should be cancelled due to timeout
        # Mark as no_trade if fill is insufficient
        if self.age >= self.config.max_wait_bars and not self.is_complete:
            # If partially filled but not complete, mark as no_trade
            if self.filled > 0:
                # Partial fill but timeout - still mark as no_trade opportunity
                self.status = OrderStatus.CANCELLED
                return OrderResult(
                    filled_qty=0.0,  # Return 0 for this attempt since already recorded
                    avg_price=0.0,
                    filled_notional=0.0,
                    slippage_pct=0.0,
                    slippage_bps=0.0,
                    status=self.status,
                )
            else:
                # No fill at all - cancel
                self.cancel("timeout")
                return OrderResult(
                    filled_qty=0.0,
                    avg_price=0.0,
                    filled_notional=0.0,
                    slippage_pct=0.0,
                    slippage_bps=0.0,
                    status=self.status,
                )
        
        target_qty = self.remaining_qty
        if target_qty <= 0:
            return OrderResult(
                filled_qty=0.0,
                avg_price=0.0,
                filled_notional=0.0,
                slippage_pct=0.0,
                slippage_bps=0.0,
                status=self.status,
            )
        
        # Determine if limit price can be hit
        can_fill = False
        
        if book:
            # Check against order book
            if self.side == OrderSide.BUY:
                # Buy: can fill if best_ask <= limit_price
                can_fill = book.best_ask is not None and book.best_ask <= self.limit_price * (1.0 + self.config.limit_price_tolerance)
            else:  # SELL
                # Sell: can fill if best_bid >= limit_price
                can_fill = book.best_bid is not None and book.best_bid >= self.limit_price * (1.0 - self.config.limit_price_tolerance)
        else:
            # Check against bar
            if isinstance(bar, pd.Series):
                bar = bar.to_dict()
            
            if self.side == OrderSide.BUY:
                # Buy: can fill if low <= limit_price
                can_fill = float(bar.get("low", 0.0)) <= self.limit_price * (1.0 + self.config.limit_price_tolerance)
            else:  # SELL
                # Sell: can fill if high >= limit_price
                can_fill = float(bar.get("high", 0.0)) >= self.limit_price * (1.0 - self.config.limit_price_tolerance)
        
        if not can_fill:
            # Limit price not hit, no fill
            self.update_age()
            return OrderResult(
                filled_qty=0.0,
                avg_price=0.0,
                filled_notional=0.0,
                slippage_pct=0.0,
                slippage_bps=0.0,
                status=self.status,
            )
        
        # Execute at limit price (or better if available)
        if book:
            # Match against book up to limit price
            executed_qty = 0.0
            total_cost = 0.0
            partial_fills = []
            
            if self.side == OrderSide.BUY:
                # Fill at asks <= limit_price
                for price, level_qty in book.asks:
                    if price > self.limit_price * (1.0 + self.config.limit_price_tolerance):
                        break
                    if executed_qty >= target_qty:
                        break
                    
                    fill_qty = min(target_qty - executed_qty, level_qty)
                    fill_price = min(price, self.limit_price)  # Fill at limit or better
                    executed_qty += fill_qty
                    total_cost += fill_price * fill_qty
                    
                    partial_fills.append({
                        "price": fill_price,
                        "qty": fill_qty,
                        "notional": fill_price * fill_qty,
                    })
            else:  # SELL
                # Fill at bids >= limit_price
                for price, level_qty in book.bids:
                    if price < self.limit_price * (1.0 - self.config.limit_price_tolerance):
                        break
                    if executed_qty >= target_qty:
                        break
                    
                    fill_qty = min(target_qty - executed_qty, level_qty)
                    fill_price = max(price, self.limit_price)  # Fill at limit or better
                    executed_qty += fill_qty
                    total_cost += fill_price * fill_qty
                    
                    partial_fills.append({
                        "price": fill_price,
                        "qty": fill_qty,
                        "notional": fill_price * fill_qty,
                    })
            
            avg_price = total_cost / executed_qty if executed_qty > 0 else self.limit_price
        else:
            # Fill at limit price
            avg_price = self.limit_price
            executed_qty = target_qty if self.config.fill_partial else 0.0
            
            if not self.config.fill_partial and target_qty > 0:
                # Can't fill without order book if partial fills disabled
                executed_qty = 0.0
        
        # Calculate slippage (should be 0 or negative for limit orders)
        reference_price = self.limit_price
        slippage_pct = (avg_price - reference_price) / reference_price if reference_price > 0 else 0.0
        
        # Update order state
        if executed_qty > 0:
            self.filled += executed_qty
            self.avg_fill_price = (
                (self.avg_fill_price * (self.filled - executed_qty) + avg_price * executed_qty) / self.filled
                if self.filled > 0
                else avg_price
            )
            
            # Record execution
            execution_record = {
                "timestamp": bar.get("timestamp", pd.Timestamp.utcnow()).isoformat() if isinstance(bar, dict) else pd.Timestamp.utcnow().isoformat(),
                "qty": executed_qty,
                "price": avg_price,
                "notional": avg_price * executed_qty,
                "limit_price": self.limit_price,
            }
            self.execution_history.append(execution_record)
            
            # Update status
            if self.is_complete:
                self.status = OrderStatus.FILLED
            else:
                self.status = OrderStatus.PARTIALLY_FILLED
        else:
            self.update_age()
        
        filled_notional = avg_price * executed_qty
        slippage_bps = slippage_pct * 10000
        
        # Prepare partial fills
        if book and partial_fills:
            result_partial_fills = partial_fills
        elif executed_qty > 0:
            execution_record = {
                "timestamp": bar.get("timestamp", pd.Timestamp.utcnow()).isoformat() if isinstance(bar, dict) else pd.Timestamp.utcnow().isoformat(),
                "qty": executed_qty,
                "price": avg_price,
                "notional": filled_notional,
                "limit_price": self.limit_price,
            }
            result_partial_fills = [execution_record]
        else:
            result_partial_fills = []
        
        return OrderResult(
            filled_qty=executed_qty,
            avg_price=avg_price,
            filled_notional=filled_notional,
            slippage_pct=slippage_pct,
            slippage_bps=slippage_bps,
            status=self.status,
            partial_fills=result_partial_fills,
        )


class StopOrder(BaseOrder):
    """Stop order - triggers when price crosses stop level, then executes as market or limit."""

    def __init__(
        self,
        symbol: str,
        side: OrderSide | str,
        qty: float,
        stop_price: float,
        *,
        order_id: str | None = None,
        timestamp: pd.Timestamp | None = None,
        config: OrderConfig | None = None,
        fill_model: FillModel | None = None,
        limit_price: float | None = None,
    ) -> None:
        """
        Initialize stop order.
        
        Args:
            stop_price: Stop trigger price
            limit_price: Optional limit price (if None, executes as market after trigger)
        """
        super().__init__(symbol, side, qty, order_id=order_id, timestamp=timestamp, config=config, fill_model=fill_model)
        self.stop_price = stop_price
        self.limit_price = limit_price
        self.triggered: bool = False
        self.trigger_price: float | None = None
        self.status = OrderStatus.PENDING

    def check_trigger(self, bar: dict[str, Any] | pd.Series, book: OrderBookSnapshot | None = None) -> bool:
        """
        Check if stop order should be triggered.
        
        Buy stop: triggers when price >= stop_price
        Sell stop: triggers when price <= stop_price
        """
        if self.triggered:
            return True
        
        current_price = None
        
        if book:
            current_price = book.mid_price
        elif isinstance(bar, pd.Series):
            current_price = float(bar.get("close", 0.0))
        elif isinstance(bar, dict):
            current_price = float(bar.get("close", bar.get("high", bar.get("low", 0.0))))
        
        if current_price is None:
            return False
        
        if self.side == OrderSide.BUY:
            # Buy stop: triggers when price crosses above stop_price
            triggered = current_price >= self.stop_price
        else:  # SELL
            # Sell stop: triggers when price crosses below stop_price
            triggered = current_price <= self.stop_price
        
        if triggered:
            self.triggered = True
            self.trigger_price = current_price
            self.status = OrderStatus.ACTIVE
            
            # If no limit_price, convert to market order
            if self.limit_price is None:
                self.config.stop_trigger_type = "market"
        
        return triggered

    def try_fill(
        self,
        bar: dict[str, Any] | pd.Series,
        book: OrderBookSnapshot | None = None,
    ) -> OrderResult:
        """
        Attempt to fill stop order.
        
        First checks if stop should be triggered, then executes as market or limit.
        """
        # Check if stop should be triggered
        if not self.triggered:
            if self.check_trigger(bar, book):
                # Just triggered, will attempt fill in next bar or immediately
                pass
            else:
                # Not triggered yet, no fill
                return OrderResult(
                    filled_qty=0.0,
                    avg_price=0.0,
                    filled_notional=0.0,
                    slippage_pct=0.0,
                    slippage_bps=0.0,
                    status=self.status,
                )
        
        # Stop triggered, execute based on trigger type
        if self.config.stop_trigger_type == "market":
            # Execute as market order
            market_order = MarketOrder(
                self.symbol,
                self.side,
                self.remaining_qty,
                order_id=self.order_id,
                timestamp=self.timestamp,
                config=self.config,
                fill_model=self.fill_model,
            )
            market_order.filled = self.filled  # Preserve existing fills
            result = market_order.try_fill(bar, book)
            
            # Update this order's state
            self.filled = market_order.filled
            self.avg_fill_price = market_order.avg_fill_price
            self.status = result.status
            self.execution_history.extend(market_order.execution_history)
            
            return result
        else:
            # Execute as limit order
            if self.limit_price is None:
                # Use stop_price as limit_price
                limit_price = self.stop_price
            else:
                limit_price = self.limit_price
            
            limit_order = LimitOrder(
                self.symbol,
                self.side,
                self.remaining_qty,
                limit_price,
                order_id=self.order_id,
                timestamp=self.timestamp,
                config=self.config,
                fill_model=self.fill_model,
            )
            limit_order.filled = self.filled
            limit_order.age = self.age
            result = limit_order.try_fill(bar, book)
            
            # Update this order's state
            self.filled = limit_order.filled
            self.avg_fill_price = limit_order.avg_fill_price
            self.status = result.status
            self.age = limit_order.age
            self.execution_history.extend(limit_order.execution_history)
            
            return result

    def to_dict(self) -> dict[str, Any]:
        """Convert stop order to dictionary with trigger info."""
        result = super().to_dict()
        result.update({
            "stop_price": self.stop_price,
            "limit_price": self.limit_price,
            "triggered": self.triggered,
            "trigger_price": self.trigger_price,
            "trigger_type": self.config.stop_trigger_type,
        })
        return result

