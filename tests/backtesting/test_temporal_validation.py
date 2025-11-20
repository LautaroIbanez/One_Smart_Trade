"""Tests for temporal validation in BacktestEngine."""
import pytest

import pandas as pd

from app.backtesting.engine import BacktestEngine, BacktestTemporalError, CandleSeries


class MockStrategy:
    """Mock strategy for testing."""
    
    def on_bar(self, ctx):
        return {"action": "hold"}


@pytest.fixture
def engine():
    """Create BacktestEngine instance with strict validation."""
    return BacktestEngine(
        use_orderbook=False,
        slippage_model="none",
        commission_rate=0.0,
        max_gap_ratio=0.1,  # 10% max gaps
        gap_threshold_multiplier=2.0,
    )


def test_raises_exception_on_non_chronological_data(engine):
    """Test that BacktestTemporalError is raised for non-chronological data."""
    # Create data with out-of-order timestamps
    dates = [
        pd.Timestamp("2020-01-01 10:00:00"),
        pd.Timestamp("2020-01-01 12:00:00"),
        pd.Timestamp("2020-01-01 11:00:00"),  # Out of order!
        pd.Timestamp("2020-01-01 13:00:00"),
    ]
    
    df = pd.DataFrame({
        "open": [100.0] * 4,
        "high": [101.0] * 4,
        "low": [99.0] * 4,
        "close": [100.5] * 4,
        "volume": [1000.0] * 4,
    }, index=dates)
    
    candle_series = CandleSeries(
        symbol="BTCUSDT",
        timeframe="1h",
        data=df,
    )
    
    strategy = MockStrategy()
    
    # Should raise BacktestTemporalError
    with pytest.raises(BacktestTemporalError) as exc_info:
        import asyncio
        asyncio.run(
            engine.run_backtest(
                "2020-01-01 10:00:00",
                "2020-01-01 13:00:00",
                instrument="BTCUSDT",
                timeframe="1h",
                strategy=strategy,
                initial_capital=10000.0,
            )
        )
    
    assert "Non-chronological" in str(exc_info.value)
    assert "details" in exc_info.value.details
    assert "prev_timestamp" in exc_info.value.details
    assert "current_timestamp" in exc_info.value.details


def test_raises_exception_on_duplicate_timestamps(engine):
    """Test that BacktestTemporalError is raised for duplicate timestamps."""
    # Create data with duplicate timestamps
    dates = [
        pd.Timestamp("2020-01-01 10:00:00"),
        pd.Timestamp("2020-01-01 11:00:00"),
        pd.Timestamp("2020-01-01 11:00:00"),  # Duplicate!
        pd.Timestamp("2020-01-01 12:00:00"),
    ]
    
    df = pd.DataFrame({
        "open": [100.0] * 4,
        "high": [101.0] * 4,
        "low": [99.0] * 4,
        "close": [100.5] * 4,
        "volume": [1000.0] * 4,
    }, index=dates)
    
    candle_series = CandleSeries(
        symbol="BTCUSDT",
        timeframe="1h",
        data=df,
    )
    
    strategy = MockStrategy()
    
    # Should raise BacktestTemporalError (bar_date <= prev_bar_ts)
    with pytest.raises(BacktestTemporalError):
        import asyncio
        asyncio.run(
            engine.run_backtest(
                "2020-01-01 10:00:00",
                "2020-01-01 12:00:00",
                instrument="BTCUSDT",
                timeframe="1h",
                strategy=strategy,
                initial_capital=10000.0,
            )
        )


def test_logs_warning_for_significant_gaps(engine, caplog):
    """Test that significant gaps are logged as warnings."""
    import logging
    
    # Create data with significant gaps (> 2× timeframe for 1h = > 2 hours)
    dates = [
        pd.Timestamp("2020-01-01 10:00:00"),
        pd.Timestamp("2020-01-01 11:00:00"),
        pd.Timestamp("2020-01-01 14:00:00"),  # 3 hour gap (significant)
        pd.Timestamp("2020-01-01 15:00:00"),
        pd.Timestamp("2020-01-01 20:00:00"),  # 5 hour gap (significant)
        pd.Timestamp("2020-01-01 21:00:00"),
    ]
    
    df = pd.DataFrame({
        "open": [100.0] * 6,
        "high": [101.0] * 6,
        "low": [99.0] * 6,
        "close": [100.5] * 6,
        "volume": [1000.0] * 6,
    }, index=dates)
    
    candle_series = CandleSeries(
        symbol="BTCUSDT",
        timeframe="1h",
        data=df,
    )
    
    strategy = MockStrategy()
    
    # Run backtest
    import asyncio
    result = asyncio.run(
        engine.run_backtest(
            "2020-01-01 10:00:00",
            "2020-01-01 21:00:00",
            instrument="BTCUSDT",
            timeframe="1h",
            strategy=strategy,
            initial_capital=10000.0,
        )
    )
    
    # Check that warnings were logged
    warning_messages = [record.message for record in caplog.records if record.levelname == "WARNING"]
    significant_gap_warnings = [msg for msg in warning_messages if "Significant gap" in msg]
    assert len(significant_gap_warnings) == 2  # Two significant gaps
    
    # Check temporal validation in result
    assert "temporal_validation" in result
    assert result["temporal_validation"]["significant_gap_count"] == 2
    assert result["temporal_validation"]["gap_count"] == 2


def test_logs_info_for_small_gaps(engine, caplog):
    """Test that small gaps (within threshold) are logged as info."""
    # Create data with small gaps (1.5× timeframe = 1.5 hours, not significant)
    dates = [
        pd.Timestamp("2020-01-01 10:00:00"),
        pd.Timestamp("2020-01-01 11:00:00"),
        pd.Timestamp("2020-01-01 12:30:00"),  # 1.5 hour gap (not significant)
        pd.Timestamp("2020-01-01 13:30:00"),  # 1 hour gap
    ]
    
    df = pd.DataFrame({
        "open": [100.0] * 4,
        "high": [101.0] * 4,
        "low": [99.0] * 4,
        "close": [100.5] * 4,
        "volume": [1000.0] * 4,
    }, index=dates)
    
    candle_series = CandleSeries(
        symbol="BTCUSDT",
        timeframe="1h",
        data=df,
    )
    
    strategy = MockStrategy()
    
    # Run backtest
    import asyncio
    result = asyncio.run(
        engine.run_backtest(
            "2020-01-01 10:00:00",
            "2020-01-01 13:30:00",
            instrument="BTCUSDT",
            timeframe="1h",
            strategy=strategy,
            initial_capital=10000.0,
        )
    )
    
    # Check that info messages were logged (not warnings)
    info_messages = [record.message for record in caplog.records if record.levelname == "INFO"]
    gap_info = [msg for msg in info_messages if "Gap detected" in msg]
    assert len(gap_info) == 1  # One gap logged as info
    
    # Check temporal validation
    assert result["temporal_validation"]["gap_count"] == 1
    assert result["temporal_validation"]["significant_gap_count"] == 0


def test_fails_temporal_validation_on_high_gap_ratio(engine):
    """Test that backtest fails temporal validation when gap ratio exceeds threshold."""
    # Create data with many gaps (more than 10% of bars)
    # 20 bars total, 5 gaps = 25% gap ratio (exceeds 10% threshold)
    dates = []
    base_date = pd.Timestamp("2020-01-01 10:00:00")
    for i in range(20):
        if i in [5, 8, 12, 15, 18]:  # Gaps at these indices
            dates.append(base_date + pd.Timedelta(hours=i + 3))  # 3 hour gap
        else:
            dates.append(base_date + pd.Timedelta(hours=i))
    
    df = pd.DataFrame({
        "open": [100.0] * 20,
        "high": [101.0] * 20,
        "low": [99.0] * 20,
        "close": [100.5] * 20,
        "volume": [1000.0] * 20,
    }, index=dates)
    
    candle_series = CandleSeries(
        symbol="BTCUSDT",
        timeframe="1h",
        data=df,
    )
    
    strategy = MockStrategy()
    
    # Run backtest
    import asyncio
    result = asyncio.run(
        engine.run_backtest(
            dates[0],
            dates[-1],
            instrument="BTCUSDT",
            timeframe="1h",
            strategy=strategy,
            initial_capital=10000.0,
        )
    )
    
    # Check that temporal validation failed
    assert result["temporal_validation"]["status"] == "FAILED_TEMPORAL_VALIDATION"
    assert result["temporal_validation"]["gap_ratio"] > engine.max_gap_ratio
    assert result["temporal_validation"]["gap_count"] == 5


def test_passes_temporal_validation_with_few_gaps(engine):
    """Test that backtest passes temporal validation with acceptable gap ratio."""
    # Create data with few gaps (less than 10% of bars)
    # 20 bars total, 1 gap = 5% gap ratio (within 10% threshold)
    dates = []
    base_date = pd.Timestamp("2020-01-01 10:00:00")
    for i in range(20):
        if i == 10:  # One gap
            dates.append(base_date + pd.Timedelta(hours=i + 3))  # 3 hour gap
        else:
            dates.append(base_date + pd.Timedelta(hours=i))
    
    df = pd.DataFrame({
        "open": [100.0] * 20,
        "high": [101.0] * 20,
        "low": [99.0] * 20,
        "close": [100.5] * 20,
        "volume": [1000.0] * 20,
    }, index=dates)
    
    candle_series = CandleSeries(
        symbol="BTCUSDT",
        timeframe="1h",
        data=df,
    )
    
    strategy = MockStrategy()
    
    # Run backtest
    import asyncio
    result = asyncio.run(
        engine.run_backtest(
            dates[0],
            dates[-1],
            instrument="BTCUSDT",
            timeframe="1h",
            strategy=strategy,
            initial_capital=10000.0,
        )
    )
    
    # Check that temporal validation passed
    assert result["temporal_validation"]["status"] == "PASS"
    assert result["temporal_validation"]["gap_ratio"] <= engine.max_gap_ratio
    assert result["temporal_validation"]["gap_count"] == 1


def test_gap_threshold_multiplier_respected(engine):
    """Test that gap threshold multiplier is correctly applied."""
    # Test with 4h timeframe: threshold = 2× 4h = 8 hours
    engine_4h = BacktestEngine(
        use_orderbook=False,
        slippage_model="none",
        commission_rate=0.0,
        max_gap_ratio=0.1,
        gap_threshold_multiplier=2.0,
    )
    
    # Create data with gaps
    dates = [
        pd.Timestamp("2020-01-01 00:00:00"),
        pd.Timestamp("2020-01-01 04:00:00"),  # Normal 4h interval
        pd.Timestamp("2020-01-01 10:00:00"),  # 6 hour gap (not significant, < 8h)
        pd.Timestamp("2020-01-01 18:00:00"),  # 8 hour gap (significant, = 8h threshold)
        pd.Timestamp("2020-01-01 22:00:00"),  # 4 hour gap
    ]
    
    df = pd.DataFrame({
        "open": [100.0] * 5,
        "high": [101.0] * 5,
        "low": [99.0] * 5,
        "close": [100.5] * 5,
        "volume": [1000.0] * 5,
    }, index=dates)
    
    candle_series = CandleSeries(
        symbol="BTCUSDT",
        timeframe="4h",
        data=df,
    )
    
    strategy = MockStrategy()
    
    # Run backtest
    import asyncio
    result = asyncio.run(
        engine_4h.run_backtest(
            dates[0],
            dates[-1],
            instrument="BTCUSDT",
            timeframe="4h",
            strategy=strategy,
            initial_capital=10000.0,
        )
    )
    
    # Check gap counts
    assert result["temporal_validation"]["gap_count"] == 2  # Two gaps total
    assert result["temporal_validation"]["significant_gap_count"] == 1  # One significant gap (>= 8h)


def test_no_gaps_in_continuous_data(engine):
    """Test that continuous data with no gaps passes validation."""
    # Create continuous hourly data
    dates = pd.date_range("2020-01-01 10:00:00", periods=24, freq="1h")
    
    df = pd.DataFrame({
        "open": [100.0] * 24,
        "high": [101.0] * 24,
        "low": [99.0] * 24,
        "close": [100.5] * 24,
        "volume": [1000.0] * 24,
    }, index=dates)
    
    candle_series = CandleSeries(
        symbol="BTCUSDT",
        timeframe="1h",
        data=df,
    )
    
    strategy = MockStrategy()
    
    # Run backtest
    import asyncio
    result = asyncio.run(
        engine.run_backtest(
            dates[0],
            dates[-1],
            instrument="BTCUSDT",
            timeframe="1h",
            strategy=strategy,
            initial_capital=10000.0,
        )
    )
    
    # Check that no gaps were detected
    assert result["temporal_validation"]["status"] == "PASS"
    assert result["temporal_validation"]["gap_count"] == 0
    assert result["temporal_validation"]["significant_gap_count"] == 0
    assert result["temporal_validation"]["gap_ratio"] == 0.0





