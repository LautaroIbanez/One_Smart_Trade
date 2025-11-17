"""Tests for periodic returns calculation in BacktestEngine."""
import pytest
from unittest.mock import Mock, AsyncMock

import pandas as pd
import numpy as np

from app.backtesting.engine import BacktestEngine, BacktestState, CandleSeries


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
        commission_rate=0.0,
    )


def test_get_equity_at_or_before_exact_match(engine):
    """Test finding equity at exact timestamp."""
    state = BacktestState(
        equity_theoretical=10000.0,
        equity_realistic=10000.0,
        peak_equity=10000.0,
        current_drawdown=0.0,
        position=None,
        open_trades=[],
        closed_trades=[],
        equity_curve_theoretical=[10000.0, 10100.0, 10200.0],
        equity_curve_realistic=[10000.0, 10100.0, 10200.0],
        equity_timestamps=[
            pd.Timestamp("2020-01-01"),
            pd.Timestamp("2020-01-02"),
            pd.Timestamp("2020-01-03"),
        ],
        returns_daily=[],
        returns_weekly=[],
        returns_monthly=[],
    )
    
    # Find equity at exact timestamp
    equity = engine._get_equity_at_or_before(pd.Timestamp("2020-01-02"), state)
    assert equity == 10100.0


def test_get_equity_at_or_before_before_timestamp(engine):
    """Test finding equity before target timestamp (gap handling)."""
    state = BacktestState(
        equity_theoretical=10000.0,
        equity_realistic=10000.0,
        peak_equity=10000.0,
        current_drawdown=0.0,
        position=None,
        open_trades=[],
        closed_trades=[],
        equity_curve_theoretical=[10000.0, 10100.0, 10200.0],
        equity_curve_realistic=[10000.0, 10100.0, 10200.0],
        equity_timestamps=[
            pd.Timestamp("2020-01-01"),
            pd.Timestamp("2020-01-02"),
            pd.Timestamp("2020-01-05"),  # Gap: missing 01-03, 01-04
        ],
        returns_daily=[],
        returns_weekly=[],
        returns_monthly=[],
    )
    
    # Find equity for date in gap (should return last value before gap)
    equity = engine._get_equity_at_or_before(pd.Timestamp("2020-01-03"), state)
    assert equity == 10100.0  # Should return value from 2020-01-02


def test_daily_returns_with_gaps(engine):
    """Test daily returns calculation with gaps in data."""
    # Create data with gaps (weekend)
    dates = pd.date_range("2020-01-01", "2020-01-10", freq="1h")
    # Remove weekend data (simulate gap)
    dates = dates[~((dates.weekday == 5) | (dates.weekday == 6))]
    
    df = pd.DataFrame({
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 1000.0,
    }, index=dates)
    
    candle_series = CandleSeries(
        symbol="BTCUSDT",
        timeframe="1h",
        data=df,
    )
    
    # Mock strategy
    strategy = MockStrategy()
    
    # Run backtest (simplified - just test the returns calculation logic)
    # We'll test the state update logic directly
    state = BacktestState(
        equity_theoretical=10000.0,
        equity_realistic=10000.0,
        peak_equity=10000.0,
        current_drawdown=0.0,
        position=None,
        open_trades=[],
        closed_trades=[],
        equity_curve_theoretical=[10000.0],
        equity_curve_realistic=[10000.0],
        equity_timestamps=[dates[0]],
        returns_daily=[],
        returns_weekly=[],
        returns_monthly=[],
    )
    
    # Simulate equity updates with gaps
    # Day 1: 10000 -> 10100
    state.update_equity(10100.0, 10100.0, dates[0] + pd.Timedelta(days=1))
    # Day 2: 10100 -> 10200 (gap between day 1 and 2)
    state.update_equity(10200.0, 10200.0, dates[0] + pd.Timedelta(days=3))  # Gap of 2 days
    
    # Calculate daily return manually
    state.last_daily_ts = dates[0]
    target_date = dates[0] + pd.Timedelta(days=3)
    
    prev_equity = engine._get_equity_at_or_before(state.last_daily_ts, state)
    assert prev_equity == 10000.0
    
    # Should use last known equity before gap
    prev_equity_gap = engine._get_equity_at_or_before(dates[0] + pd.Timedelta(days=2), state)
    assert prev_equity_gap == 10100.0  # Last value before gap


def test_weekly_returns_with_irregular_spacing(engine):
    """Test weekly returns with irregular bar spacing."""
    # Create data with irregular spacing (not exactly 7 days)
    dates = [
        pd.Timestamp("2020-01-01"),
        pd.Timestamp("2020-01-05"),  # 4 days later
        pd.Timestamp("2020-01-12"),  # 7 days later (should trigger weekly return)
        pd.Timestamp("2020-01-20"),  # 8 days later (should trigger weekly return)
    ]
    
    state = BacktestState(
        equity_theoretical=10000.0,
        equity_realistic=10000.0,
        peak_equity=10000.0,
        current_drawdown=0.0,
        position=None,
        open_trades=[],
        closed_trades=[],
        equity_curve_theoretical=[10000.0],
        equity_curve_realistic=[10000.0],
        equity_timestamps=[dates[0]],
        returns_daily=[],
        returns_weekly=[],
        returns_monthly=[],
    )
    
    # Update equity at each date
    equities = [10000.0, 10100.0, 10200.0, 10300.0]
    for i, (date, equity) in enumerate(zip(dates[1:], equities[1:], strict=False)):
        state.update_equity(equity, equity, date)
        
        # Check weekly return calculation
        if state.last_weekly_ts is None or (date - state.last_weekly_ts).days >= 7:
            if state.last_weekly_ts is not None:
                prev_equity = engine._get_equity_at_or_before(state.last_weekly_ts, state)
                if prev_equity and prev_equity > 0:
                    weekly_return = (equity - prev_equity) / prev_equity
                    state.returns_weekly.append(weekly_return)
            state.last_weekly_ts = date
    
    # Should have 2 weekly returns (from 01-01 to 01-12, and from 01-12 to 01-20)
    assert len(state.returns_weekly) == 2
    assert abs(state.returns_weekly[0] - 0.02) < 0.001  # (10200 - 10000) / 10000
    assert abs(state.returns_weekly[1] - 0.0098) < 0.001  # (10300 - 10200) / 10200


def test_monthly_returns_with_different_timeframes(engine):
    """Test monthly returns with different timeframes (1h, 4h, 1d)."""
    # Create hourly data
    dates_1h = pd.date_range("2020-01-01", "2020-02-05", freq="1h")
    
    state = BacktestState(
        equity_theoretical=10000.0,
        equity_realistic=10000.0,
        peak_equity=10000.0,
        current_drawdown=0.0,
        position=None,
        open_trades=[],
        closed_trades=[],
        equity_curve_theoretical=[10000.0],
        equity_curve_realistic=[10000.0],
        equity_timestamps=[dates_1h[0]],
        returns_daily=[],
        returns_weekly=[],
        returns_monthly=[],
    )
    
    # Update equity monthly
    monthly_dates = [
        dates_1h[0],
        dates_1h[0] + pd.Timedelta(days=30),
        dates_1h[0] + pd.Timedelta(days=60),
    ]
    monthly_equities = [10000.0, 10500.0, 11000.0]
    
    for date, equity in zip(monthly_dates[1:], monthly_equities[1:], strict=False):
        state.update_equity(equity, equity, date)
        
        # Check monthly return calculation
        if state.last_monthly_ts is None or (date - state.last_monthly_ts).days >= 30:
            if state.last_monthly_ts is not None:
                prev_equity = engine._get_equity_at_or_before(state.last_monthly_ts, state)
                if prev_equity and prev_equity > 0:
                    monthly_return = (equity - prev_equity) / prev_equity
                    state.returns_monthly.append(monthly_return)
            state.last_monthly_ts = date
    
    # Should have 2 monthly returns
    assert len(state.returns_monthly) == 2
    assert abs(state.returns_monthly[0] - 0.05) < 0.001  # (10500 - 10000) / 10000
    assert abs(state.returns_monthly[1] - 0.0476) < 0.001  # (11000 - 10500) / 10500


def test_returns_with_no_previous_value(engine):
    """Test returns calculation when no previous value exists."""
    state = BacktestState(
        equity_theoretical=10000.0,
        equity_realistic=10000.0,
        peak_equity=10000.0,
        current_drawdown=0.0,
        position=None,
        open_trades=[],
        closed_trades=[],
        equity_curve_theoretical=[10000.0],
        equity_curve_realistic=[10000.0],
        equity_timestamps=[pd.Timestamp("2020-01-01")],
        returns_daily=[],
        returns_weekly=[],
        returns_monthly=[],
    )
    
    # Try to get equity before first timestamp
    equity = engine._get_equity_at_or_before(pd.Timestamp("2019-12-31"), state)
    # Should return first value (or None if empty)
    assert equity == 10000.0 or equity is None


def test_returns_handles_zero_equity(engine):
    """Test that returns calculation handles zero or negative equity gracefully."""
    state = BacktestState(
        equity_theoretical=10000.0,
        equity_realistic=0.0,  # Zero equity
        peak_equity=10000.0,
        current_drawdown=1.0,
        position=None,
        open_trades=[],
        closed_trades=[],
        equity_curve_theoretical=[10000.0, 0.0],
        equity_curve_realistic=[10000.0, 0.0],
        equity_timestamps=[
            pd.Timestamp("2020-01-01"),
            pd.Timestamp("2020-01-02"),
        ],
        returns_daily=[],
        returns_weekly=[],
        returns_monthly=[],
    )
    
    # Should not crash when calculating return with zero equity
    state.last_daily_ts = pd.Timestamp("2020-01-01")
    target_date = pd.Timestamp("2020-01-02")
    
    prev_equity = engine._get_equity_at_or_before(state.last_daily_ts, state)
    # Should return previous equity (10000.0)
    assert prev_equity == 10000.0
    
    # Return calculation should handle zero current equity
    if prev_equity and prev_equity > 0:
        daily_return = (state.equity_realistic - prev_equity) / prev_equity
        assert daily_return == -1.0  # -100% return


