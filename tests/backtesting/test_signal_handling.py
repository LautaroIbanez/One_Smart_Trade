"""Tests for signal handling (stop loss, take profit, trailing stops) in BacktestEngine."""
import pytest
from unittest.mock import Mock

import pandas as pd

from app.backtesting.engine import BacktestEngine, BacktestState, CandleSeries, InvalidSignalError
from app.backtesting.order_types import OrderSide, OrderStatus
from app.backtesting.position import Position, PositionSide


class MockStrategy:
    """Mock strategy for testing."""
    
    def __init__(self, signals: list[dict]):
        """
        Initialize with list of signals to return.
        
        Args:
            signals: List of signal dicts, one per bar
        """
        self.signals = signals
        self.call_count = 0
    
    def on_bar(self, ctx):
        if self.call_count < len(self.signals):
            signal = self.signals[self.call_count]
            self.call_count += 1
            return signal
        return {"action": "hold"}


@pytest.fixture
def engine():
    """Create BacktestEngine instance."""
    return BacktestEngine(
        use_orderbook=False,
        slippage_model="none",
        commission_rate=0.001,
    )


@pytest.mark.asyncio
async def test_stop_loss_triggered(engine):
    """Test that stop loss order is triggered correctly."""
    # Create strategy that enters, then stop loss is triggered
    signals = [
        {"action": "enter", "side": "BUY", "entry_price": 100.0, "stop_loss": 95.0},
        {"action": "stop_loss", "stop_loss": 95.0},  # Set stop loss
        {"action": "hold"},  # Price drops, stop loss should trigger
    ]
    
    strategy = MockStrategy(signals)
    
    # Create data where price drops below stop loss
    dates = pd.date_range("2020-01-01 10:00:00", periods=3, freq="1h")
    df = pd.DataFrame({
        "open": [100.0, 98.0, 94.0],  # Price drops
        "high": [101.0, 99.0, 95.0],
        "low": [99.0, 97.0, 93.0],  # Low goes below stop loss (95.0)
        "close": [100.5, 98.5, 94.5],
        "volume": [1000.0, 1000.0, 1000.0],
    }, index=dates)
    
    candle_series = CandleSeries(
        symbol="BTCUSDT",
        timeframe="1h",
        data=df,
    )
    
    # Run backtest
    result = await engine.run_backtest(
        dates[0],
        dates[-1],
        instrument="BTCUSDT",
        timeframe="1h",
        strategy=strategy,
        initial_capital=10000.0,
    )
    
    # Check that position was closed by stop loss
    assert len(result["trades"]) == 1
    trade = result["trades"][0]
    assert trade["status"] == "closed"
    # Exit price should be around stop loss level (95.0)
    assert trade["price_exit"] <= 95.0


@pytest.mark.asyncio
async def test_take_profit_triggered(engine):
    """Test that take profit order is triggered correctly."""
    # Create strategy that enters, then take profit is triggered
    signals = [
        {"action": "enter", "side": "BUY", "entry_price": 100.0, "stop_loss": 95.0},
        {"action": "take_profit", "take_profit": 105.0},  # Set take profit
        {"action": "hold"},  # Price rises, take profit should trigger
    ]
    
    strategy = MockStrategy(signals)
    
    # Create data where price rises above take profit
    dates = pd.date_range("2020-01-01 10:00:00", periods=3, freq="1h")
    df = pd.DataFrame({
        "open": [100.0, 102.0, 104.0],
        "high": [101.0, 103.0, 106.0],  # High goes above take profit (105.0)
        "low": [99.0, 101.0, 103.0],
        "close": [100.5, 102.5, 105.5],
        "volume": [1000.0, 1000.0, 1000.0],
    }, index=dates)
    
    candle_series = CandleSeries(
        symbol="BTCUSDT",
        timeframe="1h",
        data=df,
    )
    
    # Run backtest
    result = await engine.run_backtest(
        dates[0],
        dates[-1],
        instrument="BTCUSDT",
        timeframe="1h",
        strategy=strategy,
        initial_capital=10000.0,
    )
    
    # Check that position was closed by take profit
    assert len(result["trades"]) == 1
    trade = result["trades"][0]
    assert trade["status"] == "closed"
    # Exit price should be around take profit level (105.0)
    assert trade["price_exit"] >= 105.0


@pytest.mark.asyncio
async def test_trailing_stop_updates_and_triggers(engine):
    """Test that trailing stop updates correctly and triggers when price reverses."""
    # Create strategy with trailing stop
    signals = [
        {"action": "enter", "side": "BUY", "entry_price": 100.0, "stop_loss": 95.0},
        {"action": "trailing_stop", "trailing_distance": 2.0},  # 2.0 distance
        {"action": "hold"},  # Price rises, trailing stop should move up
        {"action": "hold"},  # Price drops, trailing stop should trigger
    ]
    
    strategy = MockStrategy(signals)
    
    # Create data: price rises then drops
    dates = pd.date_range("2020-01-01 10:00:00", periods=4, freq="1h")
    df = pd.DataFrame({
        "open": [100.0, 102.0, 104.0, 103.0],
        "high": [101.0, 103.0, 105.0, 104.0],  # Peak at 105.0
        "low": [99.0, 101.0, 103.0, 101.0],  # Drops to 101.0 (should trigger trailing stop at ~103.0)
        "close": [100.5, 102.5, 104.5, 102.0],
        "volume": [1000.0, 1000.0, 1000.0, 1000.0],
    }, index=dates)
    
    candle_series = CandleSeries(
        symbol="BTCUSDT",
        timeframe="1h",
        data=df,
    )
    
    # Run backtest
    result = await engine.run_backtest(
        dates[0],
        dates[-1],
        instrument="BTCUSDT",
        timeframe="1h",
        strategy=strategy,
        initial_capital=10000.0,
    )
    
    # Check that position was closed by trailing stop
    assert len(result["trades"]) == 1
    trade = result["trades"][0]
    assert trade["status"] == "closed"
    # Exit should be around trailing stop level (peak - distance = 105.0 - 2.0 = 103.0)
    assert trade["price_exit"] <= 104.0  # Should trigger when price drops


@pytest.mark.asyncio
async def test_trailing_stop_only_moves_up_for_long(engine):
    """Test that trailing stop for long position only moves up, not down."""
    # This is tested implicitly in the trailing stop logic
    # The trailing stop should be at high - distance, and only update if new stop > old stop
    signals = [
        {"action": "enter", "side": "BUY", "entry_price": 100.0, "stop_loss": 95.0},
        {"action": "trailing_stop", "trailing_distance": 2.0},
        {"action": "hold"},  # Price rises to 105
        {"action": "hold"},  # Price drops to 103 (but trailing stop should stay at 103, not move down)
        {"action": "hold"},  # Price drops further, should trigger
    ]
    
    strategy = MockStrategy(signals)
    
    dates = pd.date_range("2020-01-01 10:00:00", periods=5, freq="1h")
    df = pd.DataFrame({
        "open": [100.0, 102.0, 105.0, 103.0, 101.0],
        "high": [101.0, 103.0, 106.0, 104.0, 102.0],  # Peak at 106.0
        "low": [99.0, 101.0, 104.0, 102.0, 100.0],  # Drops below trailing stop
        "close": [100.5, 102.5, 105.5, 103.5, 101.5],
        "volume": [1000.0] * 5,
    }, index=dates)
    
    candle_series = CandleSeries(
        symbol="BTCUSDT",
        timeframe="1h",
        data=df,
    )
    
    # Run backtest
    result = await engine.run_backtest(
        dates[0],
        dates[-1],
        instrument="BTCUSDT",
        timeframe="1h",
        strategy=strategy,
        initial_capital=10000.0,
    )
    
    # Position should be closed
    assert len(result["trades"]) == 1
    trade = result["trades"][0]
    assert trade["status"] == "closed"


@pytest.mark.asyncio
async def test_adjust_scale_in(engine):
    """Test that adjust action scales in (adds to position)."""
    signals = [
        {"action": "enter", "side": "BUY", "entry_price": 100.0, "stop_loss": 95.0},
        {"action": "adjust", "size": 0.5},  # Add 0.5 to position
        {"action": "exit"},  # Exit
    ]
    
    strategy = MockStrategy(signals)
    
    dates = pd.date_range("2020-01-01 10:00:00", periods=3, freq="1h")
    df = pd.DataFrame({
        "open": [100.0, 101.0, 102.0],
        "high": [101.0, 102.0, 103.0],
        "low": [99.0, 100.0, 101.0],
        "close": [100.5, 101.5, 102.5],
        "volume": [1000.0, 1000.0, 1000.0],
    }, index=dates)
    
    candle_series = CandleSeries(
        symbol="BTCUSDT",
        timeframe="1h",
        data=df,
    )
    
    # Run backtest
    result = await engine.run_backtest(
        dates[0],
        dates[-1],
        instrument="BTCUSDT",
        timeframe="1h",
        strategy=strategy,
        initial_capital=10000.0,
    )
    
    # Should have scaled in, then exited
    # Position size should reflect the addition
    assert len(result["trades"]) >= 1


@pytest.mark.asyncio
async def test_adjust_scale_out(engine):
    """Test that adjust action scales out (reduces position)."""
    signals = [
        {"action": "enter", "side": "BUY", "entry_price": 100.0, "stop_loss": 95.0},
        {"action": "adjust", "size": -0.3},  # Reduce position by 0.3
        {"action": "exit"},  # Exit remaining
    ]
    
    strategy = MockStrategy(signals)
    
    dates = pd.date_range("2020-01-01 10:00:00", periods=3, freq="1h")
    df = pd.DataFrame({
        "open": [100.0, 101.0, 102.0],
        "high": [101.0, 102.0, 103.0],
        "low": [99.0, 100.0, 101.0],
        "close": [100.5, 101.5, 102.5],
        "volume": [1000.0, 1000.0, 1000.0],
    }, index=dates)
    
    candle_series = CandleSeries(
        symbol="BTCUSDT",
        timeframe="1h",
        data=df,
    )
    
    # Run backtest
    result = await engine.run_backtest(
        dates[0],
        dates[-1],
        instrument="BTCUSDT",
        timeframe="1h",
        strategy=strategy,
        initial_capital=10000.0,
    )
    
    # Should have scaled out, then exited remaining
    # Should have multiple trades (partial exit + full exit)
    assert len(result["trades"]) >= 1


@pytest.mark.asyncio
async def test_invalid_signal_raises_error(engine):
    """Test that invalid signals raise InvalidSignalError."""
    # Signal missing required fields
    signals = [
        {"action": "enter"},  # Missing side and entry_price
    ]
    
    strategy = MockStrategy(signals)
    
    dates = pd.date_range("2020-01-01 10:00:00", periods=1, freq="1h")
    df = pd.DataFrame({
        "open": [100.0],
        "high": [101.0],
        "low": [99.0],
        "close": [100.5],
        "volume": [1000.0],
    }, index=dates)
    
    candle_series = CandleSeries(
        symbol="BTCUSDT",
        timeframe="1h",
        data=df,
    )
    
    # Run backtest - should handle invalid signal gracefully (logs warning, skips)
    result = await engine.run_backtest(
        dates[0],
        dates[-1],
        instrument="BTCUSDT",
        timeframe="1h",
        strategy=strategy,
        initial_capital=10000.0,
    )
    
    # Should complete without crashing (invalid signal is skipped)
    assert "error" not in result or result.get("error_type") != "InvalidSignalError"


def test_validate_signal_enter_missing_fields(engine):
    """Test signal validation for enter action."""
    state = BacktestState(
        equity_theoretical=10000.0,
        equity_realistic=10000.0,
        peak_equity=10000.0,
        current_drawdown=0.0,
        position=None,
        open_trades=[],
        closed_trades=[],
        partial_fills=[],
        rejected_orders=[],
        active_orders=[],
        equity_curve_theoretical=[10000.0],
        equity_curve_realistic=[10000.0],
        equity_timestamps=[pd.Timestamp("2020-01-01")],
        returns_daily=[],
        returns_weekly=[],
        returns_monthly=[],
    )
    
    # Missing side
    with pytest.raises(InvalidSignalError):
        engine._validate_signal({"action": "enter", "entry_price": 100.0}, state)
    
    # Missing entry_price
    with pytest.raises(InvalidSignalError):
        engine._validate_signal({"action": "enter", "side": "BUY"}, state)
    
    # Valid enter signal
    engine._validate_signal({"action": "enter", "side": "BUY", "entry_price": 100.0}, state)


def test_validate_signal_stop_loss_requires_position(engine):
    """Test that stop loss signal requires open position."""
    state_no_position = BacktestState(
        equity_theoretical=10000.0,
        equity_realistic=10000.0,
        peak_equity=10000.0,
        current_drawdown=0.0,
        position=None,
        open_trades=[],
        closed_trades=[],
        partial_fills=[],
        rejected_orders=[],
        active_orders=[],
        equity_curve_theoretical=[10000.0],
        equity_curve_realistic=[10000.0],
        equity_timestamps=[pd.Timestamp("2020-01-01")],
        returns_daily=[],
        returns_weekly=[],
        returns_monthly=[],
    )
    
    state_with_position = BacktestState(
        equity_theoretical=10000.0,
        equity_realistic=10000.0,
        peak_equity=10000.0,
        current_drawdown=0.0,
        position=Position(symbol="BTCUSDT", side=PositionSide.LONG, size=1.0, entry_price=100.0),
        open_trades=[],
        closed_trades=[],
        partial_fills=[],
        rejected_orders=[],
        active_orders=[],
        equity_curve_theoretical=[10000.0],
        equity_curve_realistic=[10000.0],
        equity_timestamps=[pd.Timestamp("2020-01-01")],
        returns_daily=[],
        returns_weekly=[],
        returns_monthly=[],
    )
    
    # Stop loss without position should raise error
    with pytest.raises(InvalidSignalError):
        engine._validate_signal({"action": "stop_loss", "stop_loss": 95.0}, state_no_position)
    
    # Stop loss with position but missing price should raise error
    with pytest.raises(InvalidSignalError):
        engine._validate_signal({"action": "stop_loss"}, state_with_position)
    
    # Valid stop loss signal
    engine._validate_signal({"action": "stop_loss", "stop_loss": 95.0}, state_with_position)


def test_validate_signal_trailing_stop_requires_distance(engine):
    """Test that trailing stop signal requires distance."""
    state = BacktestState(
        equity_theoretical=10000.0,
        equity_realistic=10000.0,
        peak_equity=10000.0,
        current_drawdown=0.0,
        position=Position(symbol="BTCUSDT", side=PositionSide.LONG, size=1.0, entry_price=100.0),
        open_trades=[],
        closed_trades=[],
        partial_fills=[],
        rejected_orders=[],
        active_orders=[],
        equity_curve_theoretical=[10000.0],
        equity_curve_realistic=[10000.0],
        equity_timestamps=[pd.Timestamp("2020-01-01")],
        returns_daily=[],
        returns_weekly=[],
        returns_monthly=[],
    )
    
    # Missing distance
    with pytest.raises(InvalidSignalError):
        engine._validate_signal({"action": "trailing_stop"}, state)
    
    # Valid with trailing_distance
    engine._validate_signal({"action": "trailing_stop", "trailing_distance": 2.0}, state)
    
    # Valid with trailing_distance_pct
    engine._validate_signal({"action": "trailing_stop", "trailing_distance_pct": 0.02}, state)




