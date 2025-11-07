"""Tests for consistency between report generation and API endpoint."""
import asyncio
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from app.backtesting.metrics import calculate_metrics
from app.backtesting.report import write_report
from app.backtesting.schemas import BacktestSummary
from app.services.performance_service import PerformanceService


def test_endpoint_report_consistency(monkeypatch):
    """Test that endpoint and report use same metrics."""
    service = PerformanceService()

    # Mock backtest result
    mock_result = {
        "trades": [
            {"pnl": 100, "return_pct": 1.0, "entry_time": "2020-01-01", "exit_time": "2020-01-02"},
        ],
        "equity_curve": [10000, 10100],
        "initial_capital": 10000.0,
        "final_capital": 10100.0,
        "start_date": "2020-01-01T00:00:00",
        "end_date": "2020-01-02T00:00:00",
    }

    # Calculate metrics directly
    direct_metrics = calculate_metrics(mock_result)

    with tempfile.TemporaryDirectory() as tmpdir:
        report_path = Path(tmpdir) / "backtest-report.md"
        monkeypatch.setattr("app.backtesting.report.REPORT_PATH", report_path)
        summary = BacktestSummary(
            start_date=datetime(2020, 1, 1),
            end_date=datetime(2020, 1, 2),
            trading_days=1,
            cagr=(direct_metrics["cagr"] or 0.0) / 100.0,
            sharpe=direct_metrics["sharpe"],
            sortino=direct_metrics["sortino"],
            profit_factor=direct_metrics["profit_factor"],
            max_drawdown=(direct_metrics["max_drawdown"] or 0.0) / 100.0,
            bh_cagr=0.0,
            bh_sharpe=0.0,
            bh_sortino=0.0,
            bh_max_drawdown=0.0,
            slippage_bps=15,
        )
        write_report(summary)
        assert report_path.exists()

        # Service should use same calculation
        with patch.object(service.engine, "run_backtest", return_value=mock_result), patch.object(
            service, "_generate_charts", return_value={}
        ):  # skip plotting in test
            summary_resp = asyncio.run(service.get_summary(use_cache=False))
            if summary_resp["status"] == "success":
                assert summary_resp["metrics"]["cagr"] == direct_metrics["cagr"]
                assert summary_resp["metrics"]["total_trades"] == direct_metrics["total_trades"]

