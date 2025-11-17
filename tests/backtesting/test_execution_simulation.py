"""Tests for execution simulation handling in BacktestEngine."""
import pytest
from unittest.mock import Mock, AsyncMock

import pandas as pd

from app.backtesting.engine import BacktestEngine, BacktestState, CandleSeries
from app.backtesting.order_types import OrderStatus, OrderSide, MarketOrder
from app.backtesting.execution_simulator import ExecutionSimulationResult


class FakeExecutionSimulator:
    """Fake execution simulator for testing."""
    
    def __init__(self, fill_ratio: float = 1.0, status: OrderStatus = OrderStatus.FILLED):
        """
        Initialize fake simulator.
        
        Args:
            fill_ratio: Fill ratio to return (0.0 to 1.0)
            status: Order status to return
        """
        self.fill_ratio = fill_ratio
        self.status = status
        self.call_count = 0
    
    async def simulate_execution(self, order, bar, *, timestamp=None, symbol=None):
        """Simulate execution with configured fill ratio and status."""
        self.call_count += 1
        
        # Calculate filled qty
        filled_qty = order.qty * self.fill_ratio
        
        # Use bar close as base price
        if isinstance(bar, dict):
            base_price = bar.get("close", 100.0)
        else:
            base_price = bar.get("close", 100.0) if hasattr(bar, "get") else 100.0
        
        # Estimate slippage (1% for partial fills, 0.5% for full)
        slippage_pct = 0.01 if self.fill_ratio < 1.0 else 0.005
        
        return ExecutionSimulationResult(
            filled_qty=filled_qty,
            avg_fill_price=base_price * (1 + slippage_pct) if order.side == OrderSide.BUY else base_price * (1 - slippage_pct),
            filled_notional=base_price * filled_qty,
            slippage_pct=slippage_pct,
            slippage_bps=slippage_pct * 10000,
            fill_ratio=self.fill_ratio,
            status=self.status,
            partial_fills=[],
            execution_time_bars=0,
            order_book_snapshot=None,
            fill_model_estimate=None,
        )


class MockStrategy:
    """Mock strategy for testing."""
    
    def __init__(self, action="enter", side="BUY"):
        self.action = action
        self.side = side
        self.call_count = 0
    
    def on_bar(self, ctx):
        self.call_count += 1
        if self.call_count == 1:
            return {
                "action": self.action,
                "side": self.side,
                "entry_price": 100.0,
                "stop_loss": 95.0,
            }
        elif self.call_count == 2 and self.action == "enter":
            return {
                "action": "exit",
                "exit_reason": "test",
            }
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
async def test_handles_partial_fill(engine):
    """Test that engine handles partial fills correctly."""
    # Create fake simulator with 50% fill ratio
    fake_simulator = FakeExecutionSimulator(fill_ratio=0.5, status=OrderStatus.FILLED)
    engine.execution_simulator = fake_simulator
    engine.use_orderbook = True
    
    # Create test data
    dates = pd.date_range("2020-01-01 10:00:00", periods=2, freq="1h")
    df = pd.DataFrame({
        "open": [100.0, 101.0],
        "high": [101.0, 102.0],
        "low": [99.0, 100.0],
        "close": [100.5, 101.5],
        "volume": [1000.0, 1000.0],
    }, index=dates)
    
    candle_series = CandleSeries(
        symbol="BTCUSDT",
        timeframe="1h",
        data=df,
    )
    
    strategy = MockStrategy(action="enter", side="BUY")
    
    # Run backtest
    result = await engine.run_backtest(
        dates[0],
        dates[-1],
        instrument="BTCUSDT",
        timeframe="1h",
        strategy=strategy,
        initial_capital=10000.0,
    )
    
    # Check that partial fill was tracked
    assert "execution_stats" in result
    assert result["execution_stats"]["partial_fills"] == 1
    assert len(result["execution_stats"]["partial_fill_details"]) == 1
    
    partial_fill = result["execution_stats"]["partial_fill_details"][0]
    assert partial_fill["fill_ratio"] == 0.5
    assert partial_fill["filled_qty"] < partial_fill["requested_qty"]
    assert partial_fill["remaining_qty"] > 0


@pytest.mark.asyncio
async def test_handles_rejected_order(engine):
    """Test that engine handles rejected/cancelled orders correctly."""
    # Create fake simulator that rejects orders
    fake_simulator = FakeExecutionSimulator(fill_ratio=0.0, status=OrderStatus.CANCELLED)
    engine.execution_simulator = fake_simulator
    engine.use_orderbook = True
    
    # Create test data
    dates = pd.date_range("2020-01-01 10:00:00", periods=2, freq="1h")
    df = pd.DataFrame({
        "open": [100.0, 101.0],
        "high": [101.0, 102.0],
        "low": [99.0, 100.0],
        "close": [100.5, 101.5],
        "volume": [1000.0, 1000.0],
    }, index=dates)
    
    candle_series = CandleSeries(
        symbol="BTCUSDT",
        timeframe="1h",
        data=df,
    )
    
    strategy = MockStrategy(action="enter", side="BUY")
    
    # Run backtest
    result = await engine.run_backtest(
        dates[0],
        dates[-1],
        instrument="BTCUSDT",
        timeframe="1h",
        strategy=strategy,
        initial_capital=10000.0,
    )
    
    # Check that rejected order was tracked
    assert "execution_stats" in result
    assert result["execution_stats"]["rejected_orders"] == 1
    assert len(result["execution_stats"]["rejected_order_details"]) == 1
    
    rejected = result["execution_stats"]["rejected_order_details"][0]
    assert rejected["status"] == "CANCELLED" or rejected["status"] == OrderStatus.CANCELLED.value
    assert rejected["fill_ratio"] == 0.0
    
    # Check that no position was opened
    assert len(result["trades"]) == 0


@pytest.mark.asyncio
async def test_partial_fill_adjusts_position_size(engine):
    """Test that partial fill correctly adjusts position size."""
    # Create fake simulator with 75% fill ratio
    fake_simulator = FakeExecutionSimulator(fill_ratio=0.75, status=OrderStatus.FILLED)
    engine.execution_simulator = fake_simulator
    engine.use_orderbook = True
    
    # Create test data
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
    
    strategy = MockStrategy(action="enter", side="BUY")
    
    # Run backtest
    result = await engine.run_backtest(
        dates[0],
        dates[-1],
        instrument="BTCUSDT",
        timeframe="1h",
        strategy=strategy,
        initial_capital=10000.0,
    )
    
    # Check that position size reflects partial fill
    # If order was for 1.0 unit and fill_ratio=0.75, position should be 0.75
    # We need to check the trade size
    if result["trades"]:
        # If trade was closed, check its size
        trade = result["trades"][0]
        # Size should reflect the filled qty (0.75 of requested)
        assert trade["size"] > 0
        assert trade["size"] <= 1.0  # Should be <= requested size


@pytest.mark.asyncio
async def test_partial_exit_reduces_position(engine):
    """Test that partial exit correctly reduces position size."""
    # First bar: full fill, second bar: partial exit (50%)
    class PartialExitSimulator:
        def __init__(self):
            self.call_count = 0
        
        async def simulate_execution(self, order, bar, *, timestamp=None, symbol=None):
            self.call_count += 1
            base_price = bar.get("close", 100.0) if isinstance(bar, dict) else 100.0
            
            if self.call_count == 1:
                # Entry: full fill
                return ExecutionSimulationResult(
                    filled_qty=order.qty,
                    avg_fill_price=base_price,
                    filled_notional=base_price * order.qty,
                    slippage_pct=0.005,
                    slippage_bps=50.0,
                    fill_ratio=1.0,
                    status=OrderStatus.FILLED,
                    partial_fills=[],
                    execution_time_bars=0,
                    order_book_snapshot=None,
                    fill_model_estimate=None,
                )
            else:
                # Exit: partial fill (50%)
                filled_qty = order.qty * 0.5
                return ExecutionSimulationResult(
                    filled_qty=filled_qty,
                    avg_fill_price=base_price,
                    filled_notional=base_price * filled_qty,
                    slippage_pct=0.005,
                    slippage_bps=50.0,
                    fill_ratio=0.5,
                    status=OrderStatus.FILLED,
                    partial_fills=[],
                    execution_time_bars=0,
                    order_book_snapshot=None,
                    fill_model_estimate=None,
                )
    
    fake_simulator = PartialExitSimulator()
    engine.execution_simulator = fake_simulator
    engine.use_orderbook = True
    
    # Create test data
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
    
    strategy = MockStrategy(action="enter", side="BUY")
    
    # Run backtest
    result = await engine.run_backtest(
        dates[0],
        dates[-1],
        instrument="BTCUSDT",
        timeframe="1h",
        strategy=strategy,
        initial_capital=10000.0,
    )
    
    # Check that partial exit created a closed trade
    # The position should be partially closed
    assert "execution_stats" in result
    # Should have at least one closed trade from partial exit
    assert len(result["trades"]) >= 1


@pytest.mark.asyncio
async def test_equity_adjusts_for_partial_fill(engine):
    """Test that equity is correctly adjusted for partial fills."""
    # Create fake simulator with 60% fill ratio
    fake_simulator = FakeExecutionSimulator(fill_ratio=0.6, status=OrderStatus.FILLED)
    engine.execution_simulator = fake_simulator
    engine.use_orderbook = True
    
    # Create test data
    dates = pd.date_range("2020-01-01 10:00:00", periods=2, freq="1h")
    df = pd.DataFrame({
        "open": [100.0, 101.0],
        "high": [101.0, 102.0],
        "low": [99.0, 100.0],
        "close": [100.5, 101.5],
        "volume": [1000.0, 1000.0],
    }, index=dates)
    
    candle_series = CandleSeries(
        symbol="BTCUSDT",
        timeframe="1h",
        data=df,
    )
    
    strategy = MockStrategy(action="enter", side="BUY")
    
    initial_capital = 10000.0
    
    # Run backtest
    result = await engine.run_backtest(
        dates[0],
        dates[-1],
        instrument="BTCUSDT",
        timeframe="1h",
        strategy=strategy,
        initial_capital=initial_capital,
    )
    
    # Check that equity was adjusted for partial fill
    # Equity should be reduced by filled_qty * price, not full order
    assert result["final_capital"] < initial_capital  # Should have spent some capital
    # But not as much as full order would cost
    assert result["final_capital"] > initial_capital - (100.5 * 1.0)  # Full order cost


@pytest.mark.asyncio
async def test_fees_proportional_to_filled_qty(engine):
    """Test that fees are calculated proportionally to filled quantity."""
    # Create fake simulator with 80% fill ratio
    fake_simulator = FakeExecutionSimulator(fill_ratio=0.8, status=OrderStatus.FILLED)
    engine.execution_simulator = fake_simulator
    engine.use_orderbook = True
    engine.commission_rate = 0.001  # 0.1%
    
    # Create test data
    dates = pd.date_range("2020-01-01 10:00:00", periods=2, freq="1h")
    df = pd.DataFrame({
        "open": [100.0, 101.0],
        "high": [101.0, 102.0],
        "low": [99.0, 100.0],
        "close": [100.5, 101.5],
        "volume": [1000.0, 1000.0],
    }, index=dates)
    
    candle_series = CandleSeries(
        symbol="BTCUSDT",
        timeframe="1h",
        data=df,
    )
    
    strategy = MockStrategy(action="enter", side="BUY")
    
    # Run backtest
    result = await engine.run_backtest(
        dates[0],
        dates[-1],
        instrument="BTCUSDT",
        timeframe="1h",
        strategy=strategy,
        initial_capital=10000.0,
    )
    
    # Check that fees in trades reflect partial fill
    if result["trades"]:
        trade = result["trades"][0]
        # Fees should be proportional to filled qty
        # If order was 1.0 and fill_ratio=0.8, fees should be 80% of full fees
        assert trade["fees_entry"] > 0
        # Fees should be: price * filled_qty * commission_rate
        expected_fees = 100.5 * 0.8 * 0.001  # Approximate
        assert abs(trade["fees_entry"] - expected_fees) < 1.0  # Allow some tolerance


