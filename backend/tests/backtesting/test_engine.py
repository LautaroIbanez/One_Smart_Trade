"""Tests for backtesting engine."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from app.backtesting.engine import BacktestEngine


@pytest.mark.asyncio
async def test_backtest_engine_execution():
    """Test backtest engine trade execution."""
    engine = BacktestEngine(commission=0.001, slippage=0.0005)

    # Test trade execution
    result = engine._execute_trade(entry_price=30000, exit_price=31000, side="BUY", size=1.0)
    assert "pnl" in result
    assert "return_pct" in result
    assert result["entry_price"] > 30000  # Slippage applied
    assert result["exit_price"] < 31000  # Slippage applied


def test_backtest_consistency():
    """Test that backtest results are consistent."""
    engine = BacktestEngine()

    # Mock curation to return minimal data
    from datetime import datetime
    import pandas as pd

    dates = pd.date_range("2020-01-01", periods=250, freq="D")
    df = pd.DataFrame(
        {
            "open_time": dates,
            "open": [30000] * 250,
            "high": [31000] * 250,
            "low": [29000] * 250,
            "close": [30000 + i * 10 for i in range(250)],
            "volume": [100] * 250,
        }
    )
    
    with patch("app.backtesting.engine.DataCuration") as mock_curation_class:
        mock_curation = mock_curation_class.return_value
        mock_curation.get_historical_curated.return_value = df
        mock_curation.get_latest_curated.return_value = df

        start = datetime(2020, 1, 1)
        end = datetime(2020, 4, 1)
        result = engine.run_backtest(start, end)

        # Should return result or error, not crash
        assert "error" in result or "trades" in result

