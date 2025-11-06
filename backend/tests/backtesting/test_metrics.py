"""Tests for backtesting metrics calculation."""
import pytest
from app.backtesting.metrics import calculate_metrics


def test_metrics_calculation():
    """Test metrics calculation with sample backtest result."""
    result = {
        "trades": [
            {"pnl": 100, "return_pct": 1.0, "entry_time": "2020-01-01", "exit_time": "2020-01-02"},
            {"pnl": -50, "return_pct": -0.5, "entry_time": "2020-01-03", "exit_time": "2020-01-04"},
            {"pnl": 150, "return_pct": 1.5, "entry_time": "2020-01-05", "exit_time": "2020-01-06"},
        ],
        "equity_curve": [10000, 10100, 10050, 10200],
        "initial_capital": 10000.0,
        "final_capital": 10200.0,
        "start_date": "2020-01-01T00:00:00",
        "end_date": "2020-01-06T00:00:00",
    }

    metrics = calculate_metrics(result)

    assert "cagr" in metrics
    assert "sharpe" in metrics
    assert "sortino" in metrics
    assert "max_drawdown" in metrics
    assert "win_rate" in metrics
    assert "profit_factor" in metrics
    assert "expectancy" in metrics
    assert "calmar" in metrics
    assert metrics["total_trades"] == 3
    assert metrics["winning_trades"] == 2
    assert metrics["losing_trades"] == 1


def test_metrics_empty_trades():
    """Test metrics with no trades."""
    result = {
        "trades": [],
        "equity_curve": [10000],
        "initial_capital": 10000.0,
        "final_capital": 10000.0,
        "start_date": "2020-01-01T00:00:00",
        "end_date": "2020-01-02T00:00:00",
    }

    metrics = calculate_metrics(result)
    assert metrics["total_trades"] == 0
    assert metrics["win_rate"] == 0.0

