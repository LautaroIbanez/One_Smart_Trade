"""Tests for PerformanceService timestamp handling in chart generation."""
import tempfile
from pathlib import Path

import pandas as pd

from app.services.performance_service import PerformanceService


def test_generate_charts_handles_mixed_and_invalid_equity_timestamps(monkeypatch):
    """_generate_charts should handle mixed-format and invalid ISO8601 timestamps without crashing."""
    service = PerformanceService()

    # Use a temporary directory to avoid polluting real report paths
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        service.reports_dir = tmp_path
        service.docs_assets_dir = tmp_path

        backtest_result = {
            "initial_capital": 10000.0,
            "equity_curve": [
                # Valid ISO8601 with fractional seconds and Z
                {"timestamp": "2024-01-01T00:00:00.123456Z", "equity_theoretical": 10000.0, "equity_realistic": 10000.0},
                # Valid ISO8601 without fractional seconds
                {"timestamp": "2024-01-01T00:01:00Z", "equity_theoretical": 10050.0, "equity_realistic": 10040.0},
                # Valid ISO8601 without timezone suffix
                {"timestamp": "2024-01-01T00:02:00", "equity_theoretical": 10100.0, "equity_realistic": 10080.0},
                # Clearly invalid timestamp that should be coerced to NaT and dropped
                {"timestamp": "not-a-timestamp", "equity_theoretical": 10150.0, "equity_realistic": 10120.0},
            ],
            "trades": [
                {"pnl": 100.0},
                {"pnl": -50.0},
            ],
            "tracking_error_series": [
                {"timestamp": "2024-01-01T00:00:00Z", "tracking_error": 0.0},
                {"timestamp": "2024-01-01T00:01:00.500000Z", "tracking_error": -10.0},
                {"timestamp": "invalid-te-ts", "tracking_error": 5.0},
            ],
        }

        charts, banners = service._generate_charts(backtest_result)

        # Should produce at least the main equity chart and not raise
        assert "equity_dual" in charts or "equity_curve" in charts
        # Tracking error panel may or may not be present depending on parsing,
        # but the function must not crash when encountering invalid timestamps.
        assert isinstance(charts, dict)
        assert isinstance(banners, list)


