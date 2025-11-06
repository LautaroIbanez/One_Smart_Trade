"""Tests for metrics consistency and reproducibility."""
import pytest
import numpy as np
from app.backtesting.metrics import calculate_metrics


def test_metrics_reproducibility():
    """Test that metrics are reproducible with same input."""
    result1 = {
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

    result2 = result1.copy()

    metrics1 = calculate_metrics(result1)
    metrics2 = calculate_metrics(result2)

    assert metrics1["cagr"] == metrics2["cagr"]
    assert metrics1["sharpe"] == metrics2["sharpe"]
    assert metrics1["win_rate"] == metrics2["win_rate"]
    assert metrics1["total_trades"] == metrics2["total_trades"]


def test_metrics_consistency():
    """Test that metrics are internally consistent."""
    result = {
        "trades": [
            {"pnl": 100, "return_pct": 1.0, "entry_time": "2020-01-01", "exit_time": "2020-01-02"},
            {"pnl": -50, "return_pct": -0.5, "entry_time": "2020-01-03", "exit_time": "2020-01-04"},
        ],
        "equity_curve": [10000, 10100, 10050],
        "initial_capital": 10000.0,
        "final_capital": 10050.0,
        "start_date": "2020-01-01T00:00:00",
        "end_date": "2020-01-04T00:00:00",
    }

    metrics = calculate_metrics(result)

    # Win rate should match winning trades / total
    assert metrics["winning_trades"] + metrics["losing_trades"] == metrics["total_trades"]
    assert metrics["win_rate"] == pytest.approx((metrics["winning_trades"] / metrics["total_trades"]) * 100, abs=0.1)

    # Total return should be positive if final > initial
    if result["final_capital"] > result["initial_capital"]:
        assert metrics["total_return"] > 0

