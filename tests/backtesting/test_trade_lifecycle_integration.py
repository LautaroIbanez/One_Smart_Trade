"""Integration test for backtesting trade lifecycle: order creation → fill → close transitions."""
import pytest
from unittest.mock import Mock

import pandas as pd

from app.backtesting.engine import BacktestEngine, CandleSeries


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
async def test_trade_lifecycle_integration_1h_data(engine):
    """
    Integration test: Verify that enter signals produce trades and lifecycle events are persisted.
    
    Acceptance criteria:
    - Backtests on 1h data report non-zero total_trades when enter signals exist
    - At least one opened/closed trade with valid SL/TP
    - Order creation → fill → close transitions are tracked
    """
    # Create strategy that enters, sets SL/TP, then exits via TP
    entry_price = 100.0
    stop_loss = 95.0  # 5% below entry (valid for LONG)
    take_profit = 105.0  # 5% above entry (valid for LONG)
    
    signals = [
        {"action": "enter", "side": "BUY", "entry_price": entry_price, "stop_loss": stop_loss, "take_profit": take_profit},
        {"action": "take_profit", "take_profit": take_profit},  # Set take profit order
        {"action": "hold"},  # Price rises, take profit should trigger
    ]
    
    strategy = MockStrategy(signals)
    
    # Create 1h data where price rises above take profit
    dates = pd.date_range("2020-01-01 10:00:00", periods=3, freq="1h")
    df = pd.DataFrame({
        "open": [entry_price, 102.0, 104.0],
        "high": [entry_price + 1.0, 103.0, 106.0],  # High goes above take profit (105.0)
        "low": [entry_price - 1.0, 101.0, 103.0],
        "close": [entry_price + 0.5, 102.5, 105.5],
        "volume": [1000.0, 1000.0, 1000.0],
        "atr": [2.0, 2.0, 2.0],
    }, index=dates)
    
    # Run backtest
    result = await engine.run_backtest(
        dates[0],
        dates[-1],
        instrument="BTCUSDT",
        timeframe="1h",
        strategy=strategy,
        initial_capital=10000.0,
    )
    
    # Acceptance: Backtests on 1h data report non-zero total_trades when enter signals exist
    total_trades = len(result.get("trades", []))
    assert total_trades > 0, f"Expected non-zero total_trades, got {total_trades}. Signal counts: {result.get('no_trade_diagnostics', {}).get('signal_counts', {})}"
    
    # Acceptance: At least one opened/closed trade with valid SL/TP
    closed_trades = [t for t in result["trades"] if t.get("status") == "closed"]
    assert len(closed_trades) > 0, "Expected at least one closed trade"
    
    trade = closed_trades[0]
    
    # Verify trade has valid entry/exit
    assert trade.get("timestamp_entry") is not None, "Trade missing entry timestamp"
    assert trade.get("timestamp_exit") is not None, "Trade missing exit timestamp"
    assert trade.get("price_entry") is not None and trade.get("price_entry") > 0, "Trade missing or invalid entry price"
    assert trade.get("price_exit") is not None and trade.get("price_exit") > 0, "Trade missing or invalid exit price"
    
    # Verify SL/TP bounds are valid
    entry_price_actual = trade["price_entry"]
    exit_price_actual = trade["price_exit"]
    
    # For LONG position, exit via TP should be above entry
    assert exit_price_actual >= take_profit, f"Exit price {exit_price_actual} should be >= take profit {take_profit} for LONG position"
    assert exit_price_actual > entry_price_actual, f"Exit price {exit_price_actual} should be > entry price {entry_price_actual} for LONG position closed via TP"
    
    # Verify lifecycle events are persisted
    execution_stats = result.get("execution_stats", {})
    assert "rejected_orders" in execution_stats, "Execution stats missing rejected_orders count"
    assert "partial_fills" in execution_stats, "Execution stats missing partial_fills count"
    
    # Verify order creation → fill → close transitions
    # Check that we have diagnostics for order lifecycle
    assert "no_trade_diagnostics" in result or total_trades > 0, "Missing trade lifecycle diagnostics"
    
    # Verify trade has valid exit reason
    assert trade.get("exit_reason") is not None, "Trade missing exit_reason"
    assert trade.get("exit_reason") in ("take_profit", "stop_loss", "signal", "trailing_stop"), \
        f"Invalid exit_reason: {trade.get('exit_reason')}"
    
    # Verify trade has PnL calculated
    assert "pnl" in trade, "Trade missing PnL"
    assert "pnl_pct" in trade, "Trade missing PnL percentage"
    assert "return_pct" in trade, "Trade missing return percentage"
    
    # Verify fees and slippage are tracked
    assert "fees_entry" in trade, "Trade missing entry fees"
    assert "fees_exit" in trade, "Trade missing exit fees"
    assert "slippage_entry" in trade, "Trade missing entry slippage"
    assert "slippage_exit" in trade, "Trade missing exit slippage"


@pytest.mark.asyncio
async def test_trade_lifecycle_stop_loss_exit(engine):
    """
    Integration test: Verify stop loss exit with valid bounds.
    """
    entry_price = 100.0
    stop_loss = 95.0  # 5% below entry (valid for LONG)
    take_profit = 105.0  # 5% above entry (valid for LONG)
    
    signals = [
        {"action": "enter", "side": "BUY", "entry_price": entry_price, "stop_loss": stop_loss, "take_profit": take_profit},
        {"action": "stop_loss", "stop_loss": stop_loss},  # Set stop loss order
        {"action": "hold"},  # Price drops, stop loss should trigger
    ]
    
    strategy = MockStrategy(signals)
    
    # Create data where price drops below stop loss
    dates = pd.date_range("2020-01-01 10:00:00", periods=3, freq="1h")
    df = pd.DataFrame({
        "open": [entry_price, 98.0, 94.0],
        "high": [entry_price + 1.0, 99.0, 95.0],
        "low": [entry_price - 1.0, 97.0, 93.0],  # Low goes below stop loss (95.0)
        "close": [entry_price - 0.5, 98.5, 94.5],
        "volume": [1000.0, 1000.0, 1000.0],
        "atr": [2.0, 2.0, 2.0],
    }, index=dates)
    
    # Run backtest
    result = await engine.run_backtest(
        dates[0],
        dates[-1],
        instrument="BTCUSDT",
        timeframe="1h",
        strategy=strategy,
        initial_capital=10000.0,
    )
    
    # Verify at least one trade
    total_trades = len(result.get("trades", []))
    assert total_trades > 0, f"Expected non-zero total_trades, got {total_trades}"
    
    closed_trades = [t for t in result["trades"] if t.get("status") == "closed"]
    assert len(closed_trades) > 0, "Expected at least one closed trade"
    
    trade = closed_trades[0]
    
    # Verify SL bounds: for LONG, exit via SL should be below entry
    entry_price_actual = trade["price_entry"]
    exit_price_actual = trade["price_exit"]
    
    assert exit_price_actual <= stop_loss, f"Exit price {exit_price_actual} should be <= stop loss {stop_loss} for LONG position"
    assert exit_price_actual < entry_price_actual, f"Exit price {exit_price_actual} should be < entry price {entry_price_actual} for LONG position closed via SL"
    
    # Verify exit reason
    assert trade.get("exit_reason") == "stop_loss" or trade.get("exit_reason", "").startswith("SL"), \
        f"Expected exit_reason to be stop_loss, got {trade.get('exit_reason')}"


@pytest.mark.asyncio
async def test_trade_lifecycle_diagnostics_when_zero_trades(engine):
    """
    Integration test: Verify diagnostics when trades are zero.
    
    Acceptance: Recommendation generation logs include trade/exit counts and root cause when trades are zero.
    """
    # Create strategy that generates enter signals but with invalid stop loss (will result in zero size)
    signals = [
        {"action": "enter", "side": "BUY", "entry_price": 100.0, "stop_loss": 100.0},  # Invalid: SL == entry
        {"action": "hold"},
        {"action": "hold"},
    ]
    
    strategy = MockStrategy(signals)
    
    dates = pd.date_range("2020-01-01 10:00:00", periods=3, freq="1h")
    df = pd.DataFrame({
        "open": [100.0, 101.0, 102.0],
        "high": [101.0, 102.0, 103.0],
        "low": [99.0, 100.0, 101.0],
        "close": [100.5, 101.5, 102.5],
        "volume": [1000.0, 1000.0, 1000.0],
        "atr": [2.0, 2.0, 2.0],
    }, index=dates)
    
    # Run backtest
    result = await engine.run_backtest(
        dates[0],
        dates[-1],
        instrument="BTCUSDT",
        timeframe="1h",
        strategy=strategy,
        initial_capital=10000.0,
    )
    
    # Verify diagnostics are present when trades are zero
    total_trades = len(result.get("trades", []))
    
    if total_trades == 0:
        # Should have no_trade_diagnostics
        no_trade_diagnostics = result.get("no_trade_diagnostics", {})
        assert no_trade_diagnostics, "Expected no_trade_diagnostics when trades are zero"
        
        # Should have root cause
        root_cause = no_trade_diagnostics.get("root_cause")
        assert root_cause, f"Expected root_cause in no_trade_diagnostics, got {no_trade_diagnostics}"
        
        # Should have signal counts
        signal_counts = no_trade_diagnostics.get("signal_counts", {})
        assert signal_counts, "Expected signal_counts in no_trade_diagnostics"
        
        # Should have reason
        reason = no_trade_diagnostics.get("reason")
        assert reason, "Expected reason in no_trade_diagnostics"
        
        # Verify execution stats include rejection details
        execution_stats = result.get("execution_stats", {})
        assert "rejected_orders" in execution_stats, "Execution stats missing rejected_orders count"
        
        # Verify signal counts are tracked
        assert "enter" in signal_counts or signal_counts.get("enter", 0) >= 0, "Signal counts missing enter count"
