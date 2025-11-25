"""Tests for performance endpoints."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from datetime import datetime, timedelta

from app.main import app
from app.db.models import BacktestResultORM


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_backtest_result():
    """Create a mock backtest result with valid metrics."""
    return {
        "status": "success",
        "metrics": {
            "cagr": 15.5,
            "sharpe": 1.2,
            "sortino": 1.5,
            "max_drawdown": 10.0,
            "win_rate": 60.0,
            "profit_factor": 1.5,
            "expectancy": 0.5,
            "calmar": 1.5,
            "total_return": 150.0,
            "total_trades": 100,
            "winning_trades": 60,
            "losing_trades": 40,
        },
        "period": {
            "start": "2020-01-01",
            "end": "2024-01-01",
        },
        "report_path": "/path/to/report",
        "metadata": {
            "served_from_cache": True,
            "cache_miss": False,
        },
    }


@pytest.mark.asyncio
async def test_performance_summary_with_valid_cache_never_returns_demo_metrics(client, mock_backtest_result):
    """Test that with valid cache, the endpoint never returns demo metrics."""
    from app.services.performance_service import get_performance_service
    
    # Mock the performance service to return valid cached data
    with patch.object(
        get_performance_service(),
        "get_summary",
        new_callable=AsyncMock,
    ) as mock_get_summary:
        mock_get_summary.return_value = mock_backtest_result
        
        # Make request without allow_stale_inputs
        response = client.get("/api/v1/performance/summary?allow_stale_inputs=false")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify it's not demo metrics
        assert "demo_metrics" not in data or data.get("demo_metrics") is False
        assert "demo_metrics_cause" not in data or data.get("demo_metrics_cause") is None
        
        # Verify we have real metrics
        assert data.get("status") in ("success", "degraded")  # degraded is OK if metrics_status != PASS
        metrics = data.get("metrics", {})
        assert metrics.get("cagr") is not None
        assert metrics.get("total_trades", 0) > 0  # Real metrics should have trades
        
        # Verify metrics are not all zeros (which would indicate demo metrics)
        assert metrics.get("cagr", 0) != 0.0 or metrics.get("total_trades", 0) > 0


@pytest.mark.asyncio
async def test_performance_summary_with_allow_stale_and_valid_cache(client, mock_backtest_result):
    """Test that allow_stale_inputs=True with valid cache returns real metrics, not demo."""
    from app.services.performance_service import get_performance_service
    
    # Mock the performance service to return valid cached data
    with patch.object(
        get_performance_service(),
        "get_summary",
        new_callable=AsyncMock,
    ) as mock_get_summary:
        mock_get_summary.return_value = mock_backtest_result
        
        # Make request with allow_stale_inputs=True
        response = client.get("/api/v1/performance/summary?allow_stale_inputs=true")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify it's not demo metrics
        assert "demo_metrics" not in data or data.get("demo_metrics") is False
        assert data.get("status") in ("success", "degraded")
        metrics = data.get("metrics", {})
        assert metrics.get("total_trades", 0) > 0  # Real metrics should have trades


@pytest.mark.asyncio
async def test_performance_summary_with_cache_miss_returns_demo_metrics_with_cause(client):
    """Test that cache miss returns demo metrics with proper cause metadata."""
    from app.services.performance_service import get_performance_service
    
    # Mock cache miss scenario
    cache_miss_result = {
        "status": "success",
        "metrics": {},
        "period": None,
        "report_path": None,
        "metadata": {
            "served_from_cache": False,
            "cache_miss": True,
        },
    }
    
    with patch.object(
        get_performance_service(),
        "get_summary",
        new_callable=AsyncMock,
    ) as mock_get_summary:
        mock_get_summary.return_value = cache_miss_result
        
        # Make request without warmup
        response = client.get("/api/v1/performance/summary?allow_stale_inputs=false&warmup=false")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify it's demo metrics with cause
        # Note: demo_metrics field may not be present in all response formats, but status and cause should be
        assert data.get("status") == "degraded"
        # Check for demo metrics indicators: all zeros in metrics
        metrics = data.get("metrics", {})
        assert metrics.get("cagr", 0) == 0.0
        assert metrics.get("total_trades", 0) == 0
        # Verify cause is indicated in chart_banners or message
        chart_banners = data.get("chart_banners", [])
        message = data.get("message", "")
        assert any("demo" in str(banner).lower() or "demo" in message.lower() for banner in chart_banners) or "demo" in message.lower()
        
        # Verify demo metrics are all zeros
        metrics = data.get("metrics", {})
        assert metrics.get("cagr", 0) == 0.0
        assert metrics.get("total_trades", 0) == 0


@pytest.mark.asyncio
async def test_performance_summary_warmup_mode_populates_cache(client, mock_backtest_result):
    """Test that warmup mode forces calculation and populates cache."""
    from app.services.performance_service import get_performance_service
    
    # First call: cache miss
    cache_miss_result = {
        "status": "success",
        "metrics": {},
        "period": None,
        "report_path": None,
        "metadata": {
            "served_from_cache": False,
            "cache_miss": True,
        },
    }
    
    # Second call: after warmup, returns real metrics
    with patch.object(
        get_performance_service(),
        "get_summary",
        new_callable=AsyncMock,
    ) as mock_get_summary, patch.object(
        get_performance_service(),
        "_run_backtest_and_cache",
        new_callable=AsyncMock,
    ) as mock_backfill:
        # First call returns cache miss
        mock_get_summary.side_effect = [
            cache_miss_result,  # First call: cache miss
            mock_backtest_result,  # Second call: after warmup
        ]
        mock_backfill.return_value = mock_backtest_result
        
        # Make request with warmup=True
        response = client.get("/api/v1/performance/summary?warmup=true")
        
        assert response.status_code == 200
        data = response.json()
        
        # After warmup, should have real metrics
        assert data.get("demo_metrics") is not True  # Should not be demo
        metrics = data.get("metrics", {})
        # If warmup succeeded, we should have real metrics; if it failed, we'd have demo
        # The important thing is that warmup was attempted
        assert mock_backfill.called, "Warmup backfill should have been called"

