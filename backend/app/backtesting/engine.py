"""Complete BacktestEngine with realistic execution, frictions, and risk management."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Protocol

import numpy as np
import pandas as pd

from app.backtesting.execution_simulator import ExecutionSimulator
from app.backtesting.order_types import BaseOrder, LimitOrder, MarketOrder, OrderSide, StopOrder
from app.backtesting.position import Position, PositionSide
from app.backtesting.tracking_error import TrackingErrorCalculator, calculate_tracking_error
from app.backtesting.unified_risk_manager import UnifiedRiskManager
from app.core.logging import logger, sanitize_log_extra
from app.data.orderbook import OrderBookRepository
from app.data.storage import get_curated_path, read_parquet
from app.observability.execution_metrics import (
    check_orderbook_fallback_alerts,
    update_execution_metrics,
)


class BacktestTemporalError(Exception):
    """Raised when temporal validation fails."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InvalidSignalError(Exception):
    """Raised when signal validation fails."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


@dataclass
class CandleSeries:
    """Normalized candle series with timestamp index."""

    symbol: str
    timeframe: str
    data: pd.DataFrame  # Must have: timestamp, open, high, low, close, volume
    data_hash: str = field(default="")

    def __post_init__(self) -> None:
        """Validate and normalize candle data."""
        def _convert_to_datetime_utc(series: pd.Series) -> pd.Series:
            """Convert timestamp series to UTC datetime, handling numeric epoch values."""
            # Check if numeric (int/float) and looks like epoch milliseconds (> 1e12)
            if pd.api.types.is_numeric_dtype(series):
                # If values are large (> 1e12), likely epoch milliseconds
                if series.min() > 1e12:
                    return pd.to_datetime(series, unit="ms", utc=True)
                else:
                    # Small numeric values might be seconds
                    return pd.to_datetime(series, unit="s", utc=True)
            else:
                # String or datetime-like: parse normally
                result = pd.to_datetime(series, utc=True)
                # If result is naive, localize to UTC
                if result.dt.tz is None:
                    result = result.dt.tz_localize("UTC")
                else:
                    result = result.dt.tz_convert("UTC")
                return result
        
        # Check if timestamp exists as index or column
        has_timestamp_index = isinstance(self.data.index, pd.DatetimeIndex)
        has_timestamp_col = "timestamp" in self.data.columns
        has_open_time_col = "open_time" in self.data.columns
        
        # If timestamp is already the index, we're good
        if has_timestamp_index:
            # Ensure required OHLCV columns exist
            required_cols = ["open", "high", "low", "close", "volume"]
            missing = [c for c in required_cols if c not in self.data.columns]
            if missing:
                raise ValueError(f"Missing required columns: {missing}")
            # Sort by timestamp
            self.data = self.data.sort_index()
            return
        
        # If timestamp is a column, use it as index
        if has_timestamp_col:
            self.data["timestamp"] = _convert_to_datetime_utc(self.data["timestamp"])
            self.data = self.data.set_index("timestamp")
        elif has_open_time_col:
            # Fallback: derive timestamp from open_time
            self.data["timestamp"] = _convert_to_datetime_utc(self.data["open_time"])
            self.data = self.data.set_index("timestamp")
        else:
            raise ValueError("No timestamp column/index or open_time column found")
        
        # Validate required OHLCV columns
        required_cols = ["open", "high", "low", "close", "volume"]
        missing = [c for c in required_cols if c not in self.data.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        # Sort by timestamp
        self.data = self.data.sort_index()

        # Calculate data hash if not provided
        if not self.data_hash:
            self.data_hash = self._calculate_hash()

    def _calculate_hash(self) -> str:
        """Calculate SHA256 hash of data for reproducibility."""
        data_str = self.data.to_csv(index=True)
        return hashlib.sha256(data_str.encode()).hexdigest()[:16]

    def stream(self) -> pd.Series:
        """Stream bars one at a time."""
        for idx, row in self.data.iterrows():
            yield row


@dataclass
class TradeFill:
    """Canonical trade fill record."""

    timestamp_entry: pd.Timestamp
    timestamp_exit: pd.Timestamp | None
    price_entry: float
    price_exit: float | None
    size: float
    side: str  # "BUY" or "SELL"
    fees_entry: float = 0.0
    fees_exit: float = 0.0
    slippage_entry: float = 0.0
    slippage_exit: float = 0.0
    status: str = "open"  # "open", "closed", "cancelled"
    exit_reason: str | None = None
    pnl: float = 0.0
    pnl_pct: float = 0.0
    return_pct: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp_entry": self.timestamp_entry.isoformat(),
            "timestamp_exit": self.timestamp_exit.isoformat() if self.timestamp_exit else None,
            "price_entry": self.price_entry,
            "price_exit": self.price_exit,
            "size": self.size,
            "side": self.side,
            "fees_entry": self.fees_entry,
            "fees_exit": self.fees_exit,
            "slippage_entry": self.slippage_entry,
            "slippage_exit": self.slippage_exit,
            "status": self.status,
            "exit_reason": self.exit_reason,
            "pnl": self.pnl,
            "pnl_pct": self.pnl_pct,
            "return_pct": self.return_pct,
        }


@dataclass
class BacktestRunRequest:
    """Canonical backtest run request."""

    instrument: str  # e.g., "BTCUSDT"
    timeframe: str  # e.g., "1h", "4h", "1d"
    start_date: pd.Timestamp
    end_date: pd.Timestamp
    strategy: Any  # Strategy protocol/object
    initial_capital: float = 10000.0
    commission_rate: float = 0.001  # 0.1% default
    slippage_model: str = "dynamic"  # "dynamic", "fixed", "none"
    fixed_slippage_bps: float = 5.0  # 5 bps if fixed
    use_orderbook: bool = True
    risk_manager: UnifiedRiskManager | None = None
    seed: int | None = None  # For reproducibility


class StrategyProtocol(Protocol):
    """Protocol for strategy objects."""

    def on_bar(self, context: dict[str, Any]) -> dict[str, Any]:
        """Generate signal from bar context. Returns signal dict with entry/exit/stop/take_profit."""
        ...


@dataclass
class PartialFill:
    """Record of a partial fill."""

    order_id: str
    requested_qty: float
    filled_qty: float
    fill_ratio: float
    timestamp: pd.Timestamp
    remaining_qty: float


@dataclass
class BacktestState:
    """State maintained during backtest execution."""

    equity_theoretical: float
    equity_realistic: float
    peak_equity: float
    current_drawdown: float
    position: Position | None
    open_trades: list[TradeFill]
    closed_trades: list[TradeFill]
    partial_fills: list[PartialFill]  # Track partial fills
    rejected_orders: list[dict[str, Any]]  # Track rejected/cancelled orders
    active_orders: list[BaseOrder]  # Track pending orders (stops, limits, trailing stops)
    equity_curve: pd.DataFrame  # DataFrame with columns: timestamp, equity_theoretical, equity_realistic, equity_divergence_pct
    returns_daily: list[float]
    returns_weekly: list[float]
    returns_monthly: list[float]
    tracking_error_stats: list[dict[str, Any]] = field(default_factory=list)  # Track periodic tracking error metrics
    last_bar_date: pd.Timestamp | None = None
    last_daily_ts: pd.Timestamp | None = None
    last_weekly_ts: pd.Timestamp | None = None
    last_monthly_ts: pd.Timestamp | None = None
    trailing_stop_price: float | None = None  # Current trailing stop price
    trailing_stop_distance: float | None = None  # Distance from peak for trailing stop

    def update_equity(self, theoretical: float, realistic: float, timestamp: pd.Timestamp) -> None:
        """Update equity and track curves with timestamp in DataFrame format."""
        self.equity_theoretical = theoretical
        self.equity_realistic = realistic
        self.peak_equity = max(self.peak_equity, realistic)
        self.current_drawdown = (self.peak_equity - realistic) / self.peak_equity if self.peak_equity > 0 else 0.0
        
        # Calculate divergence percentage
        if theoretical > 0:
            equity_divergence_pct = ((realistic - theoretical) / theoretical) * 100.0
        else:
            equity_divergence_pct = 0.0
        
        # Validate that realistic never diverges negatively without justification
        # (realistic should always be <= theoretical due to fees/slippage)
        if realistic > theoretical * 1.001:  # Allow 0.1% tolerance for rounding
            logger.warning(
                "Equity realistic exceeds theoretical without justification",
                extra={
                    "theoretical": theoretical,
                    "realistic": realistic,
                    "divergence_pct": equity_divergence_pct,
                    "timestamp": timestamp.isoformat(),
                },
            )
        
        # Append to DataFrame
        new_row = pd.DataFrame({
            "timestamp": [timestamp],
            "equity_theoretical": [theoretical],
            "equity_realistic": [realistic],
            "equity_divergence_pct": [equity_divergence_pct],
        })
        self.equity_curve = pd.concat([self.equity_curve, new_row], ignore_index=True)

    def build_context(self, bar: pd.Series) -> dict[str, Any]:
        """Build context dict for strategy."""
        return {
            "bar": bar,
            "equity": self.equity_realistic,
            "drawdown": self.current_drawdown,
            "position": self.position.to_dict() if self.position else None,
            "open_trades": len(self.open_trades),
        }


class RiskManagedPositionSizer:
    """Position sizer that adjusts based on drawdown curve."""

    def __init__(self, max_risk_pct: float = 0.01, dd_curve: list[float] | None = None) -> None:
        """
        Initialize risk-managed position sizer.

        Args:
            max_risk_pct: Maximum risk per trade (default: 1%)
            dd_curve: Optional drawdown curve for dynamic adjustment
        """
        self.max_risk_pct = max_risk_pct
        self.dd_curve = dd_curve or []

    def size(self, equity: float, signal: dict[str, Any], drawdown: float) -> float:
        """
        Calculate position size based on risk and drawdown.

        Args:
            equity: Current equity
            signal: Signal dict with stop_loss_distance
            drawdown: Current drawdown (0.0 to 1.0)

        Returns:
            Position size in units
        """
        # Reduce risk as drawdown increases (min 20% of base risk)
        risk_multiplier = max(0.2, 1.0 - (drawdown / 0.5))  # Linear reduction to 50% DD
        risk_pct = self.max_risk_pct * risk_multiplier
        dollars_risked = equity * risk_pct

        stop_loss_distance = signal.get("stop_loss_distance", 0.0)
        if stop_loss_distance <= 0:
            return 0.0
        
        size = dollars_risked / stop_loss_distance
        return size


class BacktestEngine:
    """Complete backtest engine with realistic execution and frictions."""

    def __init__(
        self,
        *,
        orderbook_repo: OrderBookRepository | None = None,
        execution_simulator: ExecutionSimulator | None = None,
        commission_rate: float = 0.001,
        slippage_model: str = "dynamic",
        fixed_slippage_bps: float = 5.0,
        use_orderbook: bool = True,
        max_gap_ratio: float = 0.1,  # 10% of bars can have gaps
        gap_threshold_multiplier: float = 2.0,  # Gap > 2× timeframe is considered significant
    ) -> None:
        """
        Initialize backtest engine.

        Args:
            orderbook_repo: Order book repository for slippage
            execution_simulator: Execution simulator (creates default if None)
            commission_rate: Commission rate (default: 0.1%)
            slippage_model: "dynamic", "fixed", or "none"
            fixed_slippage_bps: Fixed slippage in bps if model is "fixed"
            use_orderbook: Whether to use order book for execution
        """
        self.orderbook_repo = orderbook_repo or OrderBookRepository()
        self.execution_simulator = execution_simulator or ExecutionSimulator(orderbook_repo=self.orderbook_repo)
        self.commission_rate = commission_rate
        self.slippage_model = slippage_model
        self.fixed_slippage_bps = fixed_slippage_bps
        self.use_orderbook = use_orderbook
        self.max_gap_ratio = max_gap_ratio
        self.gap_threshold_multiplier = gap_threshold_multiplier

    def _load_candle_series(self, request: BacktestRunRequest) -> CandleSeries:
        """
        Load and normalize candle series from curated data.
        
        Tries to load from latest.parquet first, then falls back to the most recent
        parquet file in the curated directory if latest.parquet doesn't exist.
        Also falls back to legacy flat structure if partitioned structure is empty.
        """
        venue = "binance"  # Default venue
        symbol = request.instrument
        interval = request.timeframe
        
        # Try partitioned structure first (venue/symbol/interval/latest.parquet)
        path = get_curated_path(venue, symbol, interval)
        
        # If latest.parquet doesn't exist, find the most recent parquet file
        if not path.exists():
            curated_dir = path.parent
            if curated_dir.exists():
                # Find all parquet files in the directory
                parquet_files = sorted(curated_dir.glob("*.parquet"), key=lambda p: p.stat().st_mtime, reverse=True)
                if parquet_files:
                    path = parquet_files[0]
                    logger.info(
                        f"Using most recent curated file: {path.name} (latest.parquet not found)",
                        extra={
                            "venue": venue,
                            "symbol": symbol,
                            "interval": interval,
                            "file": path.name,
                            "directory": str(curated_dir),
                        },
                    )
                else:
                    # Fallback to legacy flat structure (interval/latest.parquet)
                    from app.data.storage import CURATED_ROOT
                    legacy_path = CURATED_ROOT / interval / "latest.parquet"
                    if legacy_path.exists():
                        path = legacy_path
                        logger.info(
                            f"Using legacy curated file structure (partitioned structure is empty)",
                            extra={
                                "venue": venue,
                                "symbol": symbol,
                                "interval": interval,
                                "legacy_path": str(legacy_path),
                            },
                        )
                    else:
                        raise FileNotFoundError(
                            f"No curated data available for {venue}/{symbol}/{interval}. "
                            f"Tried partitioned path: {curated_dir} (empty) and legacy path: {legacy_path} (not found). "
                            f"Run the curation pipeline first to generate curated data."
                        )
            else:
                # Directory doesn't exist, try legacy structure
                from app.data.storage import CURATED_ROOT
                legacy_path = CURATED_ROOT / interval / "latest.parquet"
                if legacy_path.exists():
                    path = legacy_path
                    logger.info(
                        f"Using legacy curated file structure (partitioned directory doesn't exist)",
                        extra={
                            "venue": venue,
                            "symbol": symbol,
                            "interval": interval,
                            "legacy_path": str(legacy_path),
                        },
                    )
                else:
                    raise FileNotFoundError(
                        f"No curated data directory found for {venue}/{symbol}/{interval}. "
                        f"Tried partitioned path: {curated_dir} (doesn't exist) and legacy path: {legacy_path} (not found). "
                        f"Run the curation pipeline first to generate curated data."
                    )

        logger.info(
            f"Loading candle data from: {path}",
            extra={
                "venue": venue,
                "symbol": symbol,
                "interval": interval,
                "path": str(path),
            },
        )

        df = read_parquet(path)
        
        def _convert_to_datetime_utc(series: pd.Series) -> pd.Series:
            """Convert timestamp series to UTC datetime, handling numeric epoch values."""
            # Check if numeric (int/float) and looks like epoch milliseconds (> 1e12)
            if pd.api.types.is_numeric_dtype(series):
                # If values are large (> 1e12), likely epoch milliseconds
                if series.min() > 1e12:
                    return pd.to_datetime(series, unit="ms", utc=True)
                else:
                    # Small numeric values might be seconds
                    return pd.to_datetime(series, unit="s", utc=True)
            else:
                # String or datetime-like: parse normally
                result = pd.to_datetime(series, utc=True)
                # If result is naive, localize to UTC
                if result.dt.tz is None:
                    result = result.dt.tz_localize("UTC")
                else:
                    result = result.dt.tz_convert("UTC")
                return result
        
        # Ensure timestamp column exists (fallback to open_time if needed)
        if "timestamp" not in df.columns:
            if "open_time" in df.columns:
                logger.warning(
                    "timestamp column not found, deriving from open_time",
                    extra={
                        "venue": venue,
                        "symbol": symbol,
                        "interval": interval,
                        "path": str(path),
                    },
                )
                df["timestamp"] = _convert_to_datetime_utc(df["open_time"])
            else:
                raise ValueError(
                    f"Dataset missing both 'timestamp' and 'open_time' columns. "
                    f"Available columns: {list(df.columns)}"
                )
        else:
            # Convert existing timestamp column
            df["timestamp"] = _convert_to_datetime_utc(df["timestamp"])
        
        df = df.set_index("timestamp")

        # Filter by date range
        # Ensure request dates are timezone-aware UTC for comparison
        start_date = pd.to_datetime(request.start_date, utc=True)
        if start_date.tz is None:
            start_date = start_date.tz_localize("UTC")
        else:
            start_date = start_date.tz_convert("UTC")
        
        end_date = pd.to_datetime(request.end_date, utc=True)
        if end_date.tz is None:
            end_date = end_date.tz_localize("UTC")
        else:
            end_date = end_date.tz_convert("UTC")
        
        mask = (df.index >= start_date) & (df.index <= end_date)
        df_filtered = df[mask].copy()

        if len(df_filtered) == 0:
            raise ValueError(
                f"No data in range {start_date} to {end_date}. "
                f"Available data range: {df.index.min()} to {df.index.max()}"
            )

        return CandleSeries(
            symbol=request.instrument,
            timeframe=request.timeframe,
            data=df_filtered,
        )

    def _validate_signal(self, signal: dict[str, Any], state: BacktestState) -> None:
        """
        Validate signal has required fields.
        
        Args:
            signal: Signal dictionary
            state: Current backtest state
            
        Raises:
            InvalidSignalError if signal is invalid
        """
        if not signal or not isinstance(signal, dict):
            raise InvalidSignalError("Signal must be a non-empty dictionary")
        
        action = signal.get("action")
        if not action:
            raise InvalidSignalError("Signal missing 'action' field")
        
        # Validate required fields per action
        if action == "enter":
            required = ["side", "entry_price"]
            missing = [f for f in required if f not in signal]
            if missing:
                raise InvalidSignalError(f"Enter signal missing required fields: {missing}")
        
        elif action == "exit":
            # Exit doesn't require additional fields if position exists
            if not state.position:
                raise InvalidSignalError("Exit signal requires open position")
        
        elif action == "stop_loss":
            if not state.position:
                raise InvalidSignalError("Stop loss signal requires open position")
            if "stop_loss" not in signal:
                raise InvalidSignalError("Stop loss signal missing 'stop_loss' price")
        
        elif action == "take_profit":
            if not state.position:
                raise InvalidSignalError("Take profit signal requires open position")
            if "take_profit" not in signal:
                raise InvalidSignalError("Take profit signal missing 'take_profit' price")
        
        elif action == "trailing_stop":
            if not state.position:
                raise InvalidSignalError("Trailing stop signal requires open position")
            if "trailing_distance" not in signal and "trailing_distance_pct" not in signal:
                raise InvalidSignalError("Trailing stop signal missing distance (trailing_distance or trailing_distance_pct)")
        
        elif action == "adjust":
            if not state.position:
                raise InvalidSignalError("Adjust signal requires open position")
            if "size" not in signal:
                raise InvalidSignalError("Adjust signal missing 'size' field")
        
        elif action not in ("hold", "none"):
            raise InvalidSignalError(f"Unknown action: {action}")

    def _process_active_orders(
        self,
        state: BacktestState,
        bar: pd.Series,
        bar_date: pd.Timestamp,
        request: BacktestRunRequest,
    ) -> list[BaseOrder]:
        """
        Process active orders (stops, limits, trailing stops) and check for triggers.
        
        Args:
            state: Current backtest state
            bar: Current bar data
            request: Backtest request
            
        Returns:
            List of orders to execute (triggered stops/limits)
        """
        orders_to_execute = []
        orders_to_remove = []
        
        current_price = float(bar.get("close", 0.0))
        high_price = float(bar.get("high", current_price))
        low_price = float(bar.get("low", current_price))
        
        # Update trailing stop if active
        if state.trailing_stop_distance is not None and state.position:
            if state.position.side == PositionSide.LONG:
                # Trailing stop for long: price - distance, only moves up
                new_trailing_stop = high_price - state.trailing_stop_distance
                if state.trailing_stop_price is None or new_trailing_stop > state.trailing_stop_price:
                    state.trailing_stop_price = new_trailing_stop
                
                # Check if trailing stop triggered
                if low_price <= state.trailing_stop_price:
                    # Trigger trailing stop
                    order = MarketOrder(
                        symbol=request.instrument,
                        side=OrderSide.SELL,
                        qty=state.position.size,
                        timestamp=bar_date,
                    )
                    orders_to_execute.append(order)
                    state.trailing_stop_price = None
                    state.trailing_stop_distance = None
            else:
                # Trailing stop for short: price + distance, only moves down
                new_trailing_stop = low_price + state.trailing_stop_distance
                if state.trailing_stop_price is None or new_trailing_stop < state.trailing_stop_price:
                    state.trailing_stop_price = new_trailing_stop
                
                # Check if trailing stop triggered
                if high_price >= state.trailing_stop_price:
                    # Trigger trailing stop
                    order = MarketOrder(
                        symbol=request.instrument,
                        side=OrderSide.BUY,
                        qty=state.position.size,
                        timestamp=bar_date,
                    )
                    orders_to_execute.append(order)
                    state.trailing_stop_price = None
                    state.trailing_stop_distance = None
        
        # Process stop orders
        for order in state.active_orders:
            if isinstance(order, StopOrder):
                # Check if stop order triggered
                if order.side == OrderSide.SELL:  # Stop loss for long
                    if low_price <= order.stop_price:
                        # Trigger stop order
                        market_order = MarketOrder(
                            symbol=order.symbol,
                            side=OrderSide.SELL,
                            qty=order.qty,
                            timestamp=bar_date,
                        )
                        orders_to_execute.append(market_order)
                        orders_to_remove.append(order)
                else:  # Stop loss for short
                    if high_price >= order.stop_price:
                        # Trigger stop order
                        market_order = MarketOrder(
                            symbol=order.symbol,
                            side=OrderSide.BUY,
                            qty=order.qty,
                            timestamp=bar_date,
                        )
                        orders_to_execute.append(market_order)
                        orders_to_remove.append(order)
            
            elif isinstance(order, LimitOrder):
                # Check if limit order triggered
                if order.side == OrderSide.SELL:  # Take profit for long
                    if high_price >= order.limit_price:
                        # Trigger limit order
                        market_order = MarketOrder(
                            symbol=order.symbol,
                            side=OrderSide.SELL,
                            qty=order.qty,
                            timestamp=bar_date,
                        )
                        orders_to_execute.append(market_order)
                        orders_to_remove.append(order)
                else:  # Take profit for short
                    if low_price <= order.limit_price:
                        # Trigger limit order
                        market_order = MarketOrder(
                            symbol=order.symbol,
                            side=OrderSide.BUY,
                            qty=order.qty,
                            timestamp=bar_date,
                        )
                        orders_to_execute.append(market_order)
                        orders_to_remove.append(order)
        
        # Remove triggered orders
        for order in orders_to_remove:
            state.active_orders.remove(order)
        
        return orders_to_execute

    def _get_timeframe_duration(self, timeframe: str) -> pd.Timedelta:
        """
        Get expected duration for a timeframe.
        
        Args:
            timeframe: Timeframe string (e.g., "15m", "1h", "4h", "1d")
            
        Returns:
            Timedelta representing expected duration
        """
        timeframe_map = {
            "15m": pd.Timedelta(minutes=15),
            "30m": pd.Timedelta(minutes=30),
            "1h": pd.Timedelta(hours=1),
            "4h": pd.Timedelta(hours=4),
            "1d": pd.Timedelta(days=1),
            "1w": pd.Timedelta(weeks=1),
        }
        return timeframe_map.get(timeframe, pd.Timedelta(hours=1))

    def _get_equity_at_or_before(
        self,
        target_timestamp: pd.Timestamp | None,
        state: BacktestState,
    ) -> float | None:
        """
        Get equity value at or before target timestamp.
        
        Args:
            target_timestamp: Target timestamp (can be None/NaT)
            state: BacktestState with equity curve DataFrame
            
        Returns:
            Equity value at or before timestamp, or None if not found or target is None/NaT
        """
        # Guard clause: return None if target_timestamp is None or NaT
        if target_timestamp is None or pd.isna(target_timestamp):
            return None
        
        if state.equity_curve.empty:
            return None
        
        # Filter to timestamps <= target and get last row
        filtered = state.equity_curve[state.equity_curve["timestamp"] <= target_timestamp]
        if filtered.empty:
            return None
        
        return float(filtered.iloc[-1]["equity_realistic"])

    def _validate_equity_divergence(self, state: BacktestState, timestamp: pd.Timestamp) -> None:
        """
        Validate that equity_realistic never exceeds equity_theoretical without justification.
        
        Args:
            state: Current backtest state
            timestamp: Current timestamp
            
        Raises:
            ValueError if divergence is invalid
        """
        if state.equity_curve.empty:
            return
        
        # Get latest row
        latest = state.equity_curve.iloc[-1]
        theoretical = latest["equity_theoretical"]
        realistic = latest["equity_realistic"]
        divergence_pct = latest["equity_divergence_pct"]
        
        # Realistic should never exceed theoretical by more than 0.1% (rounding tolerance)
        # In practice, realistic should always be <= theoretical due to fees/slippage
        max_allowed_divergence = 0.1  # 0.1% tolerance
        if divergence_pct > max_allowed_divergence:
            error_msg = (
                f"Invalid equity divergence: realistic ({realistic:.2f}) exceeds theoretical "
                f"({theoretical:.2f}) by {divergence_pct:.2f}% at {timestamp.isoformat()}. "
                f"Realistic should never exceed theoretical due to fees/slippage."
            )
            logger.error(error_msg)
            # Don't raise exception in production, but log error
            # In tests, this will be caught by validation

    def _estimate_slippage(
        self,
        order: BaseOrder,
        book_snapshot: Any | None,
        vol: float,
    ) -> float:
        """
        Estimate slippage based on order, book, and volatility.

        Args:
            order: Order to execute
            book_snapshot: Order book snapshot (if available)
            vol: Volatility estimate (0.0 to 1.0)

        Returns:
            Slippage as percentage (0.0 to 1.0)
        """
        if self.slippage_model == "none":
            return 0.0
        elif self.slippage_model == "fixed":
            return self.fixed_slippage_bps / 10000.0

        # Dynamic slippage
        if book_snapshot and hasattr(book_snapshot, "spread_pct"):
            spread = book_snapshot.spread_pct / 100.0 if book_snapshot.spread_pct else 0.001
            # Estimate depth cost
            depth_cost = 0.0
            if hasattr(book_snapshot, "depth_at_price"):
                depth = book_snapshot.depth_at_price(order.side.value)
                if depth > 0:
                    depth_cost = (order.qty / depth) * vol * 0.5

            return max(spread * 0.5, depth_cost)
        else:
            # Fallback: use volatility-based estimate
            return vol * 0.001  # 0.1% per unit of volatility

    async def run_backtest(
        self,
        start_date: str | pd.Timestamp | datetime,
        end_date: str | pd.Timestamp | datetime,
        *,
        instrument: str = "BTCUSDT",
        timeframe: str = "1h",
        strategy: Any | None = None,
        initial_capital: float = 10000.0,
        commission_rate: float | None = None,
        slippage_model: str | None = None,
        fixed_slippage_bps: float | None = None,
        use_orderbook: bool | None = None,
        risk_manager: UnifiedRiskManager | None = None,
        seed: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Run complete backtest with realistic execution.

        Args:
            start_date: Start date (ISO string, Timestamp, or datetime)
            end_date: End date (ISO string, Timestamp, or datetime)
            instrument: Trading instrument (default: "BTCUSDT")
            timeframe: Timeframe (default: "1h")
            strategy: Strategy object implementing StrategyProtocol
            initial_capital: Initial capital (default: 10000.0)
            commission_rate: Override commission rate
            slippage_model: Override slippage model
            fixed_slippage_bps: Override fixed slippage
            use_orderbook: Override use_orderbook flag
            risk_manager: Optional risk manager for sizing
            seed: Random seed for reproducibility
            **kwargs: Additional strategy/engine args

        Returns:
            Backtest result dict with trades, equity curves, and returns
        """
        # Normalize dates with proper UTC handling and numeric epoch support
        def _normalize_date(value) -> pd.Timestamp:
            """Normalize date to UTC timestamp, handling numeric epoch values."""
            if isinstance(value, pd.Timestamp):
                return value.tz_localize("UTC") if value.tz is None else value.tz_convert("UTC")
            elif pd.api.types.is_numeric_dtype(type(value)) or isinstance(value, (int, float)):
                # Numeric value: check if epoch milliseconds (> 1e12) or seconds
                if value > 1e12:
                    return pd.to_datetime(value, unit="ms", utc=True)
                else:
                    return pd.to_datetime(value, unit="s", utc=True)
            else:
                # String or other: parse normally with UTC
                result = pd.to_datetime(value, utc=True)
                return result.tz_localize("UTC") if result.tz is None else result.tz_convert("UTC")
        
        start_ts = _normalize_date(start_date)
        end_ts = _normalize_date(end_date)

        # Set seed if provided
        if seed is not None:
            np.random.seed(seed)

        # Build request
        request = BacktestRunRequest(
            instrument=instrument,
            timeframe=timeframe,
            start_date=start_ts,
            end_date=end_ts,
            strategy=strategy or kwargs.get("strategy"),
            initial_capital=initial_capital,
            commission_rate=commission_rate or self.commission_rate,
            slippage_model=slippage_model or self.slippage_model,
            fixed_slippage_bps=fixed_slippage_bps or self.fixed_slippage_bps,
            use_orderbook=use_orderbook if use_orderbook is not None else self.use_orderbook,
            risk_manager=risk_manager,
            seed=seed,
        )

        if not request.strategy:
            raise ValueError("strategy_required: Strategy is required for backtest")

        # Load data
        try:
            candle_series = self._load_candle_series(request)
        except FileNotFoundError as exc:
            # Re-raise FileNotFoundError as-is (it's a clear business error)
            logger.error(
                "Failed to load candle data",
                extra={
                    "error": str(exc),
                    "venue": "binance",
                    "symbol": instrument,
                    "interval": timeframe,
                },
            )
            raise
        except Exception as exc:
            logger.error(
                "Failed to load candle data",
                extra={
                    "error": str(exc),
                    "venue": "binance",
                    "symbol": instrument,
                    "interval": timeframe,
                },
            )
            raise ValueError(f"Failed to load candle data: {str(exc)}") from exc

        # Initialize state
        # Ensure initial_timestamp is valid - use first bar_date if start_ts is None/NaT
        if start_ts is None or pd.isna(start_ts):
            # Use first timestamp from candle series
            if not candle_series.data.empty:
                initial_timestamp = candle_series.data.index[0]
                # Ensure it's timezone-aware UTC
                if isinstance(initial_timestamp, pd.Timestamp):
                    if initial_timestamp.tz is None:
                        initial_timestamp = initial_timestamp.tz_localize("UTC")
                    else:
                        initial_timestamp = initial_timestamp.tz_convert("UTC")
            else:
                # Last resort: use current time
                initial_timestamp = pd.Timestamp.now(tz="UTC")
        else:
            initial_timestamp = start_ts
            # Ensure it's timezone-aware UTC
            if isinstance(initial_timestamp, pd.Timestamp):
                if initial_timestamp.tz is None:
                    initial_timestamp = initial_timestamp.tz_localize("UTC")
                else:
                    initial_timestamp = initial_timestamp.tz_convert("UTC")
        
        initial_equity_df = pd.DataFrame({
            "timestamp": [initial_timestamp],
            "equity_theoretical": [initial_capital],
            "equity_realistic": [initial_capital],
            "equity_divergence_pct": [0.0],
        })
        
        state = BacktestState(
            equity_theoretical=initial_capital,
            equity_realistic=initial_capital,
            peak_equity=initial_capital,
            current_drawdown=0.0,
            position=None,
            open_trades=[],
            closed_trades=[],
            partial_fills=[],
            rejected_orders=[],
            active_orders=[],
            equity_curve=initial_equity_df,
            returns_daily=[],
            returns_weekly=[],
            returns_monthly=[],
            tracking_error_stats=[],
        )

        # Initialize risk manager if not provided
        if not request.risk_manager:
            request.risk_manager = UnifiedRiskManager(base_capital=initial_capital)

        # Position sizer
        position_sizer = RiskManagedPositionSizer(max_risk_pct=0.01)

        # Main loop with temporal validation
        prev_bar_ts = None
        total_bars = 0
        gap_count = 0
        significant_gap_count = 0
        timeframe_duration = self._get_timeframe_duration(request.timeframe)
        gap_threshold = timeframe_duration * self.gap_threshold_multiplier

        for bar in candle_series.stream():
            bar_date = bar.name if isinstance(bar.name, pd.Timestamp) else pd.Timestamp(bar.get("timestamp", pd.Timestamp.utcnow()))
            total_bars += 1
            
            # Strict chronological validation
            if prev_bar_ts is not None and bar_date <= prev_bar_ts:
                raise BacktestTemporalError(
                    f"Non-chronological data detected: {prev_bar_ts} >= {bar_date}",
                    details={
                        "prev_timestamp": prev_bar_ts.isoformat(),
                        "current_timestamp": bar_date.isoformat(),
                        "bar_index": total_bars - 1,
                    },
                )
            
            # Detect and count gaps
            if prev_bar_ts is not None:
                gap_duration = bar_date - prev_bar_ts
                if gap_duration > timeframe_duration:
                    gap_count += 1
                    if gap_duration > gap_threshold:
                        significant_gap_count += 1
                        logger.warning(
                            "Significant gap detected",
                            extra={
                                "prev_timestamp": prev_bar_ts.isoformat(),
                                "current_timestamp": bar_date.isoformat(),
                                "gap_duration_seconds": gap_duration.total_seconds(),
                                "gap_duration_days": gap_duration.days,
                                "timeframe": request.timeframe,
                                "threshold_seconds": gap_threshold.total_seconds(),
                            },
                        )
                    else:
                        logger.info(
                            "Gap detected in data",
                            extra={
                                "prev_timestamp": prev_bar_ts.isoformat(),
                                "current_timestamp": bar_date.isoformat(),
                                "gap_duration_seconds": gap_duration.total_seconds(),
                                "gap_duration_days": gap_duration.days,
                            },
                        )
            
            prev_bar_ts = bar_date
            state.last_bar_date = bar_date

            # Build context
            ctx = state.build_context(bar)

            # Get signal from strategy
            try:
                signal = request.strategy.on_bar(ctx)
            except Exception as exc:
                logger.warning("Strategy error", extra={"error": str(exc), "bar_date": str(bar_date)})
                signal = {}

            # Validate signal
            try:
                self._validate_signal(signal, state)
            except InvalidSignalError as exc:
                logger.warning("Invalid signal", extra={"error": exc.message, "signal": signal})
                signal = {}  # Skip invalid signal

            # Process active orders (stops, limits, trailing stops)
            orders_from_active = self._process_active_orders(state, bar, bar_date, request)
            orders = orders_from_active

            # Generate orders from signal
            if signal.get("action") == "enter" and not state.position:
                # Calculate position size
                stop_loss_distance = abs(signal.get("entry_price", 0.0) - signal.get("stop_loss", 0.0))
                signal["stop_loss_distance"] = stop_loss_distance

                size = position_sizer.size(state.equity_realistic, signal, state.current_drawdown)
                if size > 0:
                    side = OrderSide.BUY if signal.get("side", "BUY") == "BUY" else OrderSide.SELL
                    order = MarketOrder(
                        symbol=request.instrument,
                        side=side,
                        qty=size,
                        timestamp=bar_date,
                    )
                    orders.append(order)

            elif signal.get("action") == "exit" and state.position:
                # Exit order
                if state.position.side == PositionSide.LONG:
                    order = MarketOrder(
                        symbol=request.instrument,
                        side=OrderSide.SELL,
                        qty=state.position.size,
                        timestamp=bar_date,
                    )
                else:
                    order = MarketOrder(
                        symbol=request.instrument,
                        side=OrderSide.BUY,
                        qty=state.position.size,
                        timestamp=bar_date,
                    )
                orders.append(order)
            
            elif signal.get("action") == "stop_loss" and state.position:
                # Stop loss order
                stop_price = signal.get("stop_loss")
                if stop_price is None:
                    logger.warning("Stop loss signal missing stop_loss price")
                else:
                    if state.position.side == PositionSide.LONG:
                        stop_order = StopOrder(
                            symbol=request.instrument,
                            side=OrderSide.SELL,
                            qty=state.position.size,
                            stop_price=stop_price,
                            timestamp=bar_date,
                        )
                    else:
                        stop_order = StopOrder(
                            symbol=request.instrument,
                            side=OrderSide.BUY,
                            qty=state.position.size,
                            stop_price=stop_price,
                            timestamp=bar_date,
                        )
                    # Cancel existing stop loss orders
                    state.active_orders = [o for o in state.active_orders if not isinstance(o, StopOrder) or o.stop_price != stop_price]
                    state.active_orders.append(stop_order)
            
            elif signal.get("action") == "take_profit" and state.position:
                # Take profit order
                tp_price = signal.get("take_profit")
                if tp_price is None:
                    logger.warning("Take profit signal missing take_profit price")
                else:
                    if state.position.side == PositionSide.LONG:
                        tp_order = LimitOrder(
                            symbol=request.instrument,
                            side=OrderSide.SELL,
                            qty=state.position.size,
                            limit_price=tp_price,
                            timestamp=bar_date,
                        )
                    else:
                        tp_order = LimitOrder(
                            symbol=request.instrument,
                            side=OrderSide.BUY,
                            qty=state.position.size,
                            limit_price=tp_price,
                            timestamp=bar_date,
                        )
                    # Cancel existing take profit orders
                    state.active_orders = [o for o in state.active_orders if not isinstance(o, LimitOrder) or getattr(o, "limit_price", None) != tp_price]
                    state.active_orders.append(tp_order)
            
            elif signal.get("action") == "trailing_stop" and state.position:
                # Trailing stop
                trailing_distance = signal.get("trailing_distance")
                trailing_distance_pct = signal.get("trailing_distance_pct")
                
                if trailing_distance is None and trailing_distance_pct is None:
                    logger.warning("Trailing stop signal missing distance")
                else:
                    # Calculate distance
                    if trailing_distance_pct is not None:
                        current_price = float(bar.get("close", 0.0))
                        trailing_distance = current_price * trailing_distance_pct
                    
                    state.trailing_stop_distance = trailing_distance
                    # Initialize trailing stop price based on current price
                    if state.position.side == PositionSide.LONG:
                        current_high = float(bar.get("high", bar.get("close", 0.0)))
                        state.trailing_stop_price = current_high - trailing_distance
                    else:
                        current_low = float(bar.get("low", bar.get("close", 0.0)))
                        state.trailing_stop_price = current_low + trailing_distance
                    # Trailing stop will be updated in _process_active_orders
            
            elif signal.get("action") == "adjust" and state.position:
                # Adjust position (scale in/out)
                adjust_size = signal.get("size", 0.0)
                if adjust_size == 0.0:
                    logger.warning("Adjust signal missing size")
                else:
                    if adjust_size > 0:
                        # Scale in (add to position)
                        side = OrderSide.BUY if state.position.side == PositionSide.LONG else OrderSide.SELL
                        order = MarketOrder(
                            symbol=request.instrument,
                            side=side,
                            qty=abs(adjust_size),
                            timestamp=bar_date,
                        )
                        orders.append(order)
                    else:
                        # Scale out (reduce position)
                        exit_qty = min(abs(adjust_size), state.position.size)
                        side = OrderSide.SELL if state.position.side == PositionSide.LONG else OrderSide.BUY
                        order = MarketOrder(
                            symbol=request.instrument,
                            side=side,
                            qty=exit_qty,
                            timestamp=bar_date,
                        )
                        orders.append(order)

            # Execute orders
            for order in orders:
                if self.use_orderbook:
                    # Use execution simulator with order book
                    exec_result = await self.execution_simulator.simulate_execution(
                        order,
                        bar.to_dict(),
                        timestamp=bar_date,
                        symbol=request.instrument,
                    )
                    
                    # Validate execution status
                    from app.backtesting.order_types import OrderStatus
                    
                    if exec_result.status != OrderStatus.FILLED:
                        # Order not filled - log and track
                        logger.warning(
                            "Order not filled",
                            extra={
                                "order_side": order.side.value,
                                "order_qty": order.qty,
                                "status": exec_result.status.value if hasattr(exec_result.status, "value") else str(exec_result.status),
                                "fill_ratio": exec_result.fill_ratio,
                                "timestamp": bar_date.isoformat(),
                            },
                        )
                        state.rejected_orders.append({
                            "timestamp": bar_date.isoformat(),
                            "order_side": order.side.value,
                            "order_qty": order.qty,
                            "status": exec_result.status.value if hasattr(exec_result.status, "value") else str(exec_result.status),
                            "fill_ratio": exec_result.fill_ratio,
                        })
                        continue  # Skip this order
                    
                    fill_price = exec_result.avg_fill_price
                    slippage_pct = exec_result.slippage_pct
                    filled_qty = exec_result.filled_qty
                    fill_ratio = exec_result.fill_ratio
                    
                    # Handle partial fills
                    if fill_ratio < 1.0:
                        remaining_qty = order.qty - filled_qty
                        logger.info(
                            "Partial fill detected",
                            extra={
                                "order_qty": order.qty,
                                "filled_qty": filled_qty,
                                "fill_ratio": fill_ratio,
                                "remaining_qty": remaining_qty,
                            },
                        )
                        
                        # Track partial fill
                        partial_fill = PartialFill(
                            order_id=str(id(order)),
                            requested_qty=order.qty,
                            filled_qty=filled_qty,
                            fill_ratio=fill_ratio,
                            timestamp=bar_date,
                            remaining_qty=remaining_qty,
                        )
                        state.partial_fills.append(partial_fill)
                        
                        # Adjust order qty to filled amount
                        order.qty = filled_qty
                else:
                    # Simple bar-based execution (assumes full fill)
                    if order.side == OrderSide.BUY:
                        fill_price = float(bar.get("high", bar.get("close", 0.0)))
                    else:
                        fill_price = float(bar.get("low", bar.get("close", 0.0)))

                    # Estimate slippage
                    vol = float(bar.get("atr", 0.0)) / float(bar.get("close", 1.0)) if bar.get("close") else 0.02
                    slippage_pct = self._estimate_slippage(order, None, vol)
                    filled_qty = order.qty
                    fill_ratio = 1.0

                # Apply commission (proportional to filled qty)
                fees = fill_price * filled_qty * request.commission_rate

                    # Update equity (theoretical: no frictions, realistic: with frictions)
                if order.side == OrderSide.BUY:
                    # Entry
                    if not state.position:
                        # New position with filled qty
                        state.position = Position(
                            symbol=request.instrument,
                            side=PositionSide.LONG,
                            initial_fill_price=fill_price,
                            initial_qty=filled_qty,  # Use filled qty, not requested
                            opened_at=bar_date,
                        )
                        trade = TradeFill(
                            timestamp_entry=bar_date,
                            timestamp_exit=None,
                            price_entry=fill_price,
                            price_exit=None,
                            size=filled_qty,  # Use filled qty
                            side="BUY",
                            fees_entry=fees,
                            fees_exit=0.0,
                            slippage_entry=slippage_pct,
                            slippage_exit=0.0,
                        )
                        state.open_trades.append(trade)

                        # Theoretical: no costs
                        state.equity_theoretical -= fill_price * filled_qty
                        # Realistic: with costs
                        state.equity_realistic -= fill_price * filled_qty * (1 + slippage_pct) - fees
                    else:
                        # Adding to existing position (partial fill of additional order)
                        # Average entry price
                        total_cost = (state.position.entry_price * state.position.size) + (fill_price * filled_qty)
                        total_size = state.position.size + filled_qty
                        new_entry_price = total_cost / total_size if total_size > 0 else fill_price
                        
                        state.position.size = total_size
                        state.position.entry_price = new_entry_price
                        
                        # Update existing trade or create new one
                        if state.open_trades:
                            trade = state.open_trades[-1]
                            trade.size = total_size
                            # Average fees and slippage
                            trade.fees_entry = (trade.fees_entry * (total_size - filled_qty) + fees) / total_size
                            trade.slippage_entry = (trade.slippage_entry * (total_size - filled_qty) + slippage_pct * filled_qty) / total_size
                        
                        # Update equity
                        state.equity_theoretical -= fill_price * filled_qty
                        state.equity_realistic -= fill_price * filled_qty * (1 + slippage_pct) - fees
                else:
                    # Exit
                    if state.position:
                        entry_price = state.position.entry_price
                        position_size = state.position.size
                        
                        # Handle partial exit
                        if filled_qty < position_size:
                            # Partial exit - reduce position size
                            exit_ratio = filled_qty / position_size
                            pnl = (fill_price - entry_price) * filled_qty if state.position.side == PositionSide.LONG else (entry_price - fill_price) * filled_qty
                            pnl_pct = (pnl / (entry_price * filled_qty)) * 100 if entry_price > 0 else 0.0
                            
                            # Update position size
                            state.position.size = position_size - filled_qty
                            
                            # Create partial exit trade record
                            if state.open_trades:
                                trade = state.open_trades[0]
                                # Record partial exit
                                partial_exit = TradeFill(
                                    timestamp_entry=trade.timestamp_entry,
                                    timestamp_exit=bar_date,
                                    price_entry=trade.price_entry,
                                    price_exit=fill_price,
                                    size=filled_qty,
                                    side=trade.side,
                                    fees_entry=trade.fees_entry * exit_ratio,
                                    fees_exit=fees,
                                    slippage_entry=trade.slippage_entry,
                                    slippage_exit=slippage_pct,
                                    status="closed",
                                    exit_reason=signal.get("exit_reason", "partial_exit"),
                                    pnl=pnl - (trade.fees_entry * exit_ratio) - fees,
                                    pnl_pct=pnl_pct,
                                    return_pct=(fill_price / entry_price - 1) * 100 if state.position.side == PositionSide.LONG else (entry_price / fill_price - 1) * 100,
                                )
                                state.closed_trades.append(partial_exit)
                                
                                # Update remaining trade
                                trade.size = state.position.size
                                trade.fees_entry = trade.fees_entry * (1 - exit_ratio)
                            
                            # Update equity
                            state.equity_theoretical += fill_price * filled_qty
                            state.equity_realistic += fill_price * filled_qty * (1 - slippage_pct) - fees
                        else:
                            # Full exit
                            pnl = (fill_price - entry_price) * filled_qty if state.position.side == PositionSide.LONG else (entry_price - fill_price) * filled_qty
                            pnl_pct = (pnl / (entry_price * filled_qty)) * 100 if entry_price > 0 else 0.0

                            # Close trade
                            if state.open_trades:
                                trade = state.open_trades.pop(0)
                                trade.timestamp_exit = bar_date
                                trade.price_exit = fill_price
                                trade.fees_exit = fees
                                trade.slippage_exit = slippage_pct
                                trade.status = "closed"
                                trade.exit_reason = signal.get("exit_reason", "signal")
                                trade.pnl = pnl - trade.fees_entry - fees  # Subtract both entry and exit fees
                                trade.pnl_pct = pnl_pct
                                trade.return_pct = (fill_price / entry_price - 1) * 100 if state.position.side == PositionSide.LONG else (entry_price / fill_price - 1) * 100
                                state.closed_trades.append(trade)

                            # Theoretical: no costs
                            state.equity_theoretical += fill_price * filled_qty
                            # Realistic: with costs
                            state.equity_realistic += fill_price * filled_qty * (1 - slippage_pct) - fees

                            state.position = None
                            # Clear active orders when position closed
                            state.active_orders = []
                            state.trailing_stop_price = None
                            state.trailing_stop_distance = None

            # Update equity curves
            state.update_equity(state.equity_theoretical, state.equity_realistic, bar_date)

            # Calculate tracking error after updating equity curves
            if len(state.equity_curve) >= 2:
                # Get bars_per_year based on timeframe for annualization
                bars_per_year_map = {
                    "15m": 365 * 24 * 4,  # 4 bars per hour
                    "30m": 365 * 24 * 2,  # 2 bars per hour
                    "1h": 365 * 24,  # 24 bars per day
                    "4h": 365 * 6,  # 6 bars per day
                    "1d": 365,  # Daily
                    "1w": 52,  # Weekly
                }
                bars_per_year = bars_per_year_map.get(request.timeframe, 252)  # Default to 252 for daily

                tracking_stats = TrackingErrorCalculator.from_curves(
                    theoretical=state.equity_curve["equity_theoretical"],
                    realistic=state.equity_curve["equity_realistic"],
                    bars_per_year=bars_per_year,
                )
                state.tracking_error_stats.append(tracking_stats.to_dict())

            # Calculate periodic returns based on actual dates
            # Daily returns
            if state.last_daily_ts is None or (bar_date - state.last_daily_ts).days >= 1:
                if state.last_daily_ts is not None:
                    prev_equity = self._get_equity_at_or_before(state.last_daily_ts, state)
                    if prev_equity is not None and prev_equity > 0:
                        daily_return = (state.equity_realistic - prev_equity) / prev_equity
                        state.returns_daily.append(daily_return)
                state.last_daily_ts = bar_date

            # Weekly returns
            if state.last_weekly_ts is None or (bar_date - state.last_weekly_ts).days >= 7:
                if state.last_weekly_ts is not None:
                    prev_equity = self._get_equity_at_or_before(state.last_weekly_ts, state)
                    if prev_equity is not None and prev_equity > 0:
                        weekly_return = (state.equity_realistic - prev_equity) / prev_equity
                        state.returns_weekly.append(weekly_return)
                state.last_weekly_ts = bar_date

            # Monthly returns
            if state.last_monthly_ts is None or (bar_date - state.last_monthly_ts).days >= 30:
                if state.last_monthly_ts is not None:
                    prev_equity = self._get_equity_at_or_before(state.last_monthly_ts, state)
                    if prev_equity is not None and prev_equity > 0:
                        monthly_return = (state.equity_realistic - prev_equity) / prev_equity
                        state.returns_monthly.append(monthly_return)
                state.last_monthly_ts = bar_date
            
            # Validate equity divergence after each update
            self._validate_equity_divergence(state, bar_date)

        # Post-processing temporal validation
        gap_ratio = gap_count / total_bars if total_bars > 0 else 0.0
        temporal_status = "PASS"
        
        if gap_ratio > self.max_gap_ratio:
            temporal_status = "FAILED_TEMPORAL_VALIDATION"
            logger.error(
                "Backtest failed temporal validation: gap ratio exceeds threshold",
                extra={
                    "gap_ratio": gap_ratio,
                    "max_gap_ratio": self.max_gap_ratio,
                    "gap_count": gap_count,
                    "significant_gap_count": significant_gap_count,
                    "total_bars": total_bars,
                },
            )
            # Optionally raise exception or mark as failed
            # raise BacktestTemporalError(
            #     f"Gap ratio ({gap_ratio:.2%}) exceeds maximum ({self.max_gap_ratio:.2%})",
            #     details={
            #         "gap_ratio": gap_ratio,
            #         "max_gap_ratio": self.max_gap_ratio,
            #         "gap_count": gap_count,
            #         "significant_gap_count": significant_gap_count,
            #         "total_bars": total_bars,
            #     },
            # )

        # Build result
        trades = [t.to_dict() for t in state.closed_trades]
        final_capital = state.equity_realistic
        
        equity_curve_df = state.equity_curve.copy()
        equity_curve_dict: list[dict[str, Any]] = []
        equity_curve_theoretical_records: list[dict[str, Any]] = []
        equity_curve_realistic_records: list[dict[str, Any]] = []
        tracking_error_metrics: dict[str, Any] | None = None
        tracking_error_series_records: list[dict[str, Any]] = []
        tracking_error_cumulative_records: list[dict[str, Any]] = []
        timestamps_list: list[pd.Timestamp] = []
        
        if not equity_curve_df.empty:
            equity_curve_df["timestamp"] = pd.to_datetime(equity_curve_df["timestamp"])
            timestamps_list = [pd.Timestamp(ts).tz_localize(None) for ts in equity_curve_df["timestamp"].tolist()]
            
            for idx, row in enumerate(equity_curve_df.itertuples(index=False)):
                ts = timestamps_list[idx]
                iso_ts = ts.isoformat()
                theoretical_val = float(getattr(row, "equity_theoretical"))
                realistic_val = float(getattr(row, "equity_realistic"))
                divergence_pct_val = float(getattr(row, "equity_divergence_pct"))
                
                equity_curve_dict.append(
                    {
                        "timestamp": iso_ts,
                        "equity_theoretical": theoretical_val,
                        "equity_realistic": realistic_val,
                        "equity_divergence_pct": divergence_pct_val,
                    }
                )
                equity_curve_theoretical_records.append({"timestamp": iso_ts, "equity": theoretical_val})
                equity_curve_realistic_records.append({"timestamp": iso_ts, "equity": realistic_val})
        
        # Calculate summary metrics from equity curve
        if not equity_curve_df.empty:
            max_divergence_pct = float(equity_curve_df["equity_divergence_pct"].max())
            min_divergence_pct = float(equity_curve_df["equity_divergence_pct"].min())
            avg_divergence_pct = float(equity_curve_df["equity_divergence_pct"].mean())
        else:
            max_divergence_pct = 0.0
            min_divergence_pct = 0.0
            avg_divergence_pct = 0.0

        # Calculate final tracking error metrics for entire period
        tracking_error = None
        if len(equity_curve_df) >= 2:
            bars_per_year_map = {
                "15m": 365 * 24 * 4,
                "30m": 365 * 24 * 2,
                "1h": 365 * 24,
                "4h": 365 * 6,
                "1d": 365,
                "1w": 52,
            }
            bars_per_year = bars_per_year_map.get(request.timeframe, 252)
            tracking_error_calculator = TrackingErrorCalculator.from_curves(
                theoretical=equity_curve_df["equity_theoretical"],
                realistic=equity_curve_df["equity_realistic"],
                bars_per_year=bars_per_year,
            )
            tracking_error = tracking_error_calculator.to_dict()
            
            # Detailed tracking error diagnostics and series for visualization
            tracking_error_payload = calculate_tracking_error(
                equity_curve_df["equity_theoretical"],
                equity_curve_df["equity_realistic"],
            )
            tracking_error_series = tracking_error_payload.pop("tracking_error", [])
            tracking_error_metrics = tracking_error_payload
            
            if tracking_error_series:
                cumulative_values = np.cumsum(tracking_error_series).tolist()
                for ts, value, cumulative in zip(timestamps_list, tracking_error_series, cumulative_values):
                    iso_ts = ts.isoformat()
                    tracking_error_series_records.append(
                        {"timestamp": iso_ts, "tracking_error": float(value)}
                    )
                    tracking_error_cumulative_records.append(
                        {"timestamp": iso_ts, "tracking_error_cumulative": float(cumulative)}
                    )
        
        # Update Prometheus metrics and check alerts for orderbook fallbacks
        orderbook_fallback_count = self.execution_simulator.orderbook_fallback_count
        orderbook_alerts: list[dict[str, Any]] = []
        if orderbook_fallback_count > 0:
            # Update metrics for each warning reason
            for warning in self.execution_simulator.orderbook_warnings:
                update_execution_metrics(
                    symbol=instrument,
                    order_type="all",
                    orderbook_fallback_count=1,
                    orderbook_fallback_reason=warning.reason,
                )
            
            # Check for alerts
            orderbook_alerts = check_orderbook_fallback_alerts(
                symbol=instrument,
                fallback_count=orderbook_fallback_count,
                total_bars=total_bars,
                context="backtest",
            )
            
            # Log alerts if any
            for alert in orderbook_alerts:
                alert_message = alert.get("message", "Orderbook fallback alert")
                alert_payload = dict(alert)
                alert_payload["alert_message"] = alert_message
                # Avoid reserved LogRecord keys when logging externally-built payloads.
                logger.warning(alert_message, extra=sanitize_log_extra(alert_payload))

        return {
            "start_date": start_ts.isoformat(),
            "end_date": end_ts.isoformat(),
            "symbol": instrument,
            "venue": "binance",  # Default venue
            "interval": timeframe,
            "initial_capital": initial_capital,
            "final_capital": final_capital,
            "trades": trades,
            "equity_curve": equity_curve_dict,  # DataFrame as list of dicts
            "equity_curve_theoretical": equity_curve_theoretical_records,
            "equity_curve_realistic": equity_curve_realistic_records,
            "equity_theoretical": state.equity_curve["equity_theoretical"].tolist() if not state.equity_curve.empty else [],  # Legacy compatibility
            "equity_realistic": state.equity_curve["equity_realistic"].tolist() if not state.equity_curve.empty else [],  # Legacy compatibility
            "equity_divergence_metrics": {
                "max_divergence_pct": max_divergence_pct,
                "min_divergence_pct": min_divergence_pct,
                "avg_divergence_pct": avg_divergence_pct,
            },
            "returns_per_period": {
                "daily": state.returns_daily,
                "weekly": state.returns_weekly,
                "monthly": state.returns_monthly,
            },
            "data_hash": candle_series.data_hash,
            "seed": seed,
            "temporal_validation": {
                "status": temporal_status,
                "gap_count": gap_count,
                "significant_gap_count": significant_gap_count,
                "total_bars": total_bars,
                "gap_ratio": gap_ratio,
                "max_gap_ratio": self.max_gap_ratio,
            },
            "execution_stats": {
                "partial_fills": len(state.partial_fills),
                "rejected_orders": len(state.rejected_orders),
                "partial_fill_details": [
                    {
                        "timestamp": pf.timestamp.isoformat(),
                        "requested_qty": pf.requested_qty,
                        "filled_qty": pf.filled_qty,
                        "fill_ratio": pf.fill_ratio,
                        "remaining_qty": pf.remaining_qty,
                    }
                    for pf in state.partial_fills
                ],
                "rejected_order_details": state.rejected_orders,
                "orderbook_fallback_count": orderbook_fallback_count,
                "orderbook_fallback_pct": (orderbook_fallback_count / total_bars * 100.0) if total_bars > 0 else 0.0,
                "orderbook_warnings": [w.to_dict() for w in self.execution_simulator.orderbook_warnings],
                "orderbook_alerts": orderbook_alerts,
            },
            "metadata": {
                "instrument": instrument,
                "timeframe": timeframe,
                "commission_rate": request.commission_rate,
                "slippage_model": request.slippage_model,
                "use_orderbook": request.use_orderbook,
            },
            "tracking_error": tracking_error,
            "tracking_error_metrics": tracking_error_metrics,
            "tracking_error_stats": state.tracking_error_stats,
            "tracking_error_series": tracking_error_series_records,
            "tracking_error_cumulative": tracking_error_cumulative_records,
        }
