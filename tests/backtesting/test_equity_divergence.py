"""Tests for equity divergence validation in BacktestEngine."""
import pytest
from unittest.mock import Mock

import pandas as pd

from app.backtesting.engine import BacktestEngine, BacktestState, CandleSeries
from app.backtesting.position import Position, PositionSide


class MockStrategy:
    """Mock strategy for testing."""
    
    def on_bar(self, ctx):
        return {"action": "hold"}


@pytest.fixture
def engine():
    """Create BacktestEngine instance."""
    return BacktestEngine(
        use_orderbook=False,
        slippage_model="none",
        commission_rate=0.001,  # 0.1% commission
    )


def test_equity_curve_dataframe_structure(engine):
    """Test that equity curve is stored as DataFrame with correct columns."""
    initial_timestamp = pd.Timestamp("2020-01-01")
    initial_capital = 10000.0
    
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
    )
    
    # Verify structure
    assert isinstance(state.equity_curve, pd.DataFrame)
    assert list(state.equity_curve.columns) == ["timestamp", "equity_theoretical", "equity_realistic", "equity_divergence_pct"]
    assert len(state.equity_curve) == 1


def test_equity_divergence_calculation(engine):
    """Test that equity divergence is calculated correctly."""
    initial_timestamp = pd.Timestamp("2020-01-01")
    initial_capital = 10000.0
    
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
    )
    
    # Update equity with fees (realistic < theoretical)
    theoretical = 10100.0
    realistic = 10090.0  # 10.0 in fees (0.1% of 10000)
    timestamp = pd.Timestamp("2020-01-02")
    
    state.update_equity(theoretical, realistic, timestamp)
    
    # Check divergence
    latest = state.equity_curve.iloc[-1]
    assert latest["equity_theoretical"] == theoretical
    assert latest["equity_realistic"] == realistic
    expected_divergence = ((realistic - theoretical) / theoretical) * 100.0
    assert abs(latest["equity_divergence_pct"] - expected_divergence) < 0.01


def test_equity_realistic_never_exceeds_theoretical(engine):
    """Test that equity_realistic never exceeds equity_theoretical without justification."""
    initial_timestamp = pd.Timestamp("2020-01-01")
    initial_capital = 10000.0
    
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
    )
    
    # Try to set realistic > theoretical (should log warning but not crash)
    theoretical = 10000.0
    realistic = 10050.0  # 0.5% higher (invalid)
    timestamp = pd.Timestamp("2020-01-02")
    
    # This should log a warning but not raise exception
    state.update_equity(theoretical, realistic, timestamp)
    
    # Check that divergence is recorded
    latest = state.equity_curve.iloc[-1]
    assert latest["equity_divergence_pct"] > 0.0  # Positive divergence (invalid)


@pytest.mark.asyncio
async def test_backtest_equity_divergence_with_fees(engine):
    """Test that backtest correctly shows realistic < theoretical due to fees."""
    # Create strategy that enters and exits
    class EnterExitStrategy:
        def __init__(self):
            self.call_count = 0
        
        def on_bar(self, ctx):
            self.call_count += 1
            if self.call_count == 1:
                return {"action": "enter", "side": "BUY", "entry_price": 100.0, "stop_loss": 95.0}
            elif self.call_count == 2:
                return {"action": "exit"}
            return {"action": "hold"}
    
    strategy = EnterExitStrategy()
    
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
    
    # Run backtest with commission
    engine.commission_rate = 0.001  # 0.1%
    
    result = await engine.run_backtest(
        dates[0],
        dates[-1],
        instrument="BTCUSDT",
        timeframe="1h",
        strategy=strategy,
        initial_capital=10000.0,
    )
    
    # Check equity curve structure
    assert "equity_curve" in result
    assert isinstance(result["equity_curve"], list)
    
    # Check divergence metrics
    assert "equity_divergence_metrics" in result
    metrics = result["equity_divergence_metrics"]
    assert "max_divergence_pct" in metrics
    assert "min_divergence_pct" in metrics
    assert "avg_divergence_pct" in metrics
    
    # Realistic should be <= theoretical (allowing small rounding)
    if result["equity_curve"]:
        for row in result["equity_curve"]:
            theoretical = row["equity_theoretical"]
            realistic = row["equity_realistic"]
            divergence = row["equity_divergence_pct"]
            
            # Divergence should be <= 0.1% (tolerance for rounding)
            assert divergence <= 0.1, f"Divergence {divergence}% exceeds tolerance at {row['timestamp']}"
            
            # Realistic should be <= theoretical (allowing 0.1% tolerance)
            assert realistic <= theoretical * 1.001, f"Realistic {realistic} exceeds theoretical {theoretical}"


@pytest.mark.asyncio
async def test_equity_divergence_increases_with_trades(engine):
    """Test that equity divergence increases with more trades (more fees)."""
    # Create strategy with multiple trades
    class MultiTradeStrategy:
        def __init__(self):
            self.call_count = 0
        
        def on_bar(self, ctx):
            self.call_count += 1
            if self.call_count == 1:
                return {"action": "enter", "side": "BUY", "entry_price": 100.0, "stop_loss": 95.0}
            elif self.call_count == 2:
                return {"action": "exit"}
            elif self.call_count == 3:
                return {"action": "enter", "side": "BUY", "entry_price": 100.0, "stop_loss": 95.0}
            elif self.call_count == 4:
                return {"action": "exit"}
            return {"action": "hold"}
    
    strategy = MultiTradeStrategy()
    
    # Create test data
    dates = pd.date_range("2020-01-01 10:00:00", periods=5, freq="1h")
    df = pd.DataFrame({
        "open": [100.0, 101.0, 102.0, 100.0, 101.0],
        "high": [101.0, 102.0, 103.0, 101.0, 102.0],
        "low": [99.0, 100.0, 101.0, 99.0, 100.0],
        "close": [100.5, 101.5, 102.5, 100.5, 101.5],
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
    
    # Check that divergence increases (becomes more negative) with more trades
    if len(result["equity_curve"]) > 1:
        first_divergence = result["equity_curve"][0]["equity_divergence_pct"]
        last_divergence = result["equity_curve"][-1]["equity_divergence_pct"]
        
        # After trades with fees, divergence should be more negative
        assert last_divergence <= first_divergence


def test_get_equity_at_or_before_with_dataframe(engine):
    """Test _get_equity_at_or_before works with DataFrame structure."""
    initial_timestamp = pd.Timestamp("2020-01-01")
    
    equity_df = pd.DataFrame({
        "timestamp": [
            pd.Timestamp("2020-01-01"),
            pd.Timestamp("2020-01-02"),
            pd.Timestamp("2020-01-05"),  # Gap
        ],
        "equity_theoretical": [10000.0, 10100.0, 10200.0],
        "equity_realistic": [10000.0, 10090.0, 10180.0],
        "equity_divergence_pct": [0.0, -0.099, -0.196],
    })
    
    state = BacktestState(
        equity_theoretical=10200.0,
        equity_realistic=10180.0,
        peak_equity=10200.0,
        current_drawdown=0.0,
        position=None,
        open_trades=[],
        closed_trades=[],
        partial_fills=[],
        rejected_orders=[],
        active_orders=[],
        equity_curve=equity_df,
        returns_daily=[],
        returns_weekly=[],
        returns_monthly=[],
    )
    
    # Find equity for date in gap
    equity = engine._get_equity_at_or_before(pd.Timestamp("2020-01-03"), state)
    assert equity == 10090.0  # Should return value from 2020-01-02
    
    # Find equity for exact date
    equity = engine._get_equity_at_or_before(pd.Timestamp("2020-01-02"), state)
    assert equity == 10090.0


def test_equity_curve_query_by_timestamp(engine):
    """Test that equity curve DataFrame can be queried by timestamp."""
    initial_timestamp = pd.Timestamp("2020-01-01")
    
    equity_df = pd.DataFrame({
        "timestamp": pd.date_range("2020-01-01", periods=10, freq="1h"),
        "equity_theoretical": [10000.0 + i * 10 for i in range(10)],
        "equity_realistic": [10000.0 + i * 9 for i in range(10)],  # 1.0 less per bar (fees)
        "equity_divergence_pct": [-i * 0.01 for i in range(10)],
    })
    
    state = BacktestState(
        equity_theoretical=10090.0,
        equity_realistic=10081.0,
        peak_equity=10090.0,
        current_drawdown=0.0,
        position=None,
        open_trades=[],
        closed_trades=[],
        partial_fills=[],
        rejected_orders=[],
        active_orders=[],
        equity_curve=equity_df,
        returns_daily=[],
        returns_weekly=[],
        returns_monthly=[],
    )
    
    # Query by timestamp range
    start_ts = pd.Timestamp("2020-01-01 02:00:00")
    end_ts = pd.Timestamp("2020-01-01 05:00:00")
    
    filtered = state.equity_curve[
        (state.equity_curve["timestamp"] >= start_ts) &
        (state.equity_curve["timestamp"] <= end_ts)
    ]
    
    assert len(filtered) == 4  # 02:00, 03:00, 04:00, 05:00
    
    # Check divergence is always <= 0.1% (realistic <= theoretical with tolerance)
    assert (filtered["equity_divergence_pct"] <= 0.1).all()  # Allow 0.1% tolerance


@pytest.mark.asyncio
async def test_ci_equity_realistic_never_exceeds_theoretical(engine):
    """
    CI validation: equity_realistic should never exceed equity_theoretical without justification.
    
    This test ensures that fees and slippage are properly applied, so realistic
    should always be <= theoretical (allowing 0.1% tolerance for rounding).
    """
    # Create strategy with multiple trades to accumulate fees
    class MultiTradeStrategy:
        def __init__(self):
            self.call_count = 0
        
        def on_bar(self, ctx):
            self.call_count += 1
            if self.call_count == 1:
                return {"action": "enter", "side": "BUY", "entry_price": 100.0, "stop_loss": 95.0}
            elif self.call_count == 2:
                return {"action": "exit"}
            elif self.call_count == 3:
                return {"action": "enter", "side": "BUY", "entry_price": 100.0, "stop_loss": 95.0}
            elif self.call_count == 4:
                return {"action": "exit"}
            return {"action": "hold"}
    
    strategy = MultiTradeStrategy()
    
    # Create test data
    dates = pd.date_range("2020-01-01 10:00:00", periods=5, freq="1h")
    df = pd.DataFrame({
        "open": [100.0, 101.0, 102.0, 100.0, 101.0],
        "high": [101.0, 102.0, 103.0, 101.0, 102.0],
        "low": [99.0, 100.0, 101.0, 99.0, 100.0],
        "close": [100.5, 101.5, 102.5, 100.5, 101.5],
        "volume": [1000.0] * 5,
    }, index=dates)
    
    candle_series = CandleSeries(
        symbol="BTCUSDT",
        timeframe="1h",
        data=df,
    )
    
    # Run backtest with commission
    engine.commission_rate = 0.001  # 0.1% commission
    
    result = await engine.run_backtest(
        dates[0],
        dates[-1],
        instrument="BTCUSDT",
        timeframe="1h",
        strategy=strategy,
        initial_capital=10000.0,
    )
    
    # CI Validation: Check every row in equity curve
    assert "equity_curve" in result
    assert isinstance(result["equity_curve"], list)
    assert len(result["equity_curve"]) > 0
    
    max_divergence_found = -float("inf")
    violations = []
    
    for row in result["equity_curve"]:
        theoretical = row["equity_theoretical"]
        realistic = row["equity_realistic"]
        divergence_pct = row["equity_divergence_pct"]
        timestamp = row["timestamp"]
        
        max_divergence_found = max(max_divergence_found, divergence_pct)
        
        # CI Rule: Divergence should be <= 0.1% (tolerance for rounding)
        if divergence_pct > 0.1:
            violations.append({
                "timestamp": timestamp,
                "theoretical": theoretical,
                "realistic": realistic,
                "divergence_pct": divergence_pct,
            })
        
        # CI Rule: Realistic should be <= theoretical * 1.001 (0.1% tolerance)
        if realistic > theoretical * 1.001:
            violations.append({
                "timestamp": timestamp,
                "theoretical": theoretical,
                "realistic": realistic,
                "divergence_pct": divergence_pct,
                "reason": "realistic exceeds theoretical",
            })
    
    # Report violations
    if violations:
        violation_msg = "\n".join([
            f"  {v['timestamp']}: theoretical={v['theoretical']:.2f}, "
            f"realistic={v['realistic']:.2f}, divergence={v['divergence_pct']:.2f}%"
            for v in violations
        ])
        pytest.fail(
            f"CI Validation Failed: Found {len(violations)} equity divergence violations.\n"
            f"Max divergence found: {max_divergence_found:.2f}%\n"
            f"Violations:\n{violation_msg}\n"
            f"Realistic should never exceed theoretical due to fees/slippage."
        )
    
    # Check summary metrics
    assert "equity_divergence_metrics" in result
    metrics = result["equity_divergence_metrics"]
    assert metrics["max_divergence_pct"] <= 0.1, f"Max divergence {metrics['max_divergence_pct']:.2f}% exceeds 0.1% tolerance"
    
    # Verify that realistic is always <= theoretical in summary
    if result["equity_theoretical"] and result["equity_realistic"]:
        for i, (theo, real) in enumerate(zip(result["equity_theoretical"], result["equity_realistic"])):
            assert real <= theo * 1.001, f"Row {i}: realistic {real:.2f} exceeds theoretical {theo:.2f}"

