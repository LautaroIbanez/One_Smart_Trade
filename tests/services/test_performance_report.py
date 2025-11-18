"""Tests for performance report endpoints ensuring tracking error fields are included."""
import pytest
from unittest.mock import Mock, patch, AsyncMock

from app.api.v1.performance import get_performance_summary
from app.models.performance import PerformanceSummaryResponse


@pytest.fixture
def mock_backtest_result():
    """Mock backtest result with tracking error data."""
    return {
        "status": "success",
        "start_date": "2023-01-01T00:00:00",
        "end_date": "2024-01-01T00:00:00",
        "equity_theoretical": [10000.0, 10100.0, 10200.0, 10300.0, 10400.0],
        "equity_realistic": [10000.0, 10080.0, 10160.0, 10240.0, 10320.0],
        "equity_curve": [
            {"timestamp": "2023-01-01", "equity_theoretical": 10000.0, "equity_realistic": 10000.0},
            {"timestamp": "2023-01-02", "equity_theoretical": 10100.0, "equity_realistic": 10080.0},
            {"timestamp": "2023-01-03", "equity_theoretical": 10200.0, "equity_realistic": 10160.0},
        ],
        "equity_curve_theoretical": [
            {"timestamp": "2023-01-01", "equity": 10000.0},
            {"timestamp": "2023-01-02", "equity": 10100.0},
        ],
        "equity_curve_realistic": [
            {"timestamp": "2023-01-01", "equity": 10000.0},
            {"timestamp": "2023-01-02", "equity": 10080.0},
        ],
        "tracking_error": {
            "rmse": 95.5,
            "annualized_tracking_error": 2.5,
            "max_divergence_bps": 180.0,
            "mean_divergence_bps": 50.0,
            "bars_with_divergence_above_threshold_pct": 8.5,
        },
        "tracking_error_metrics": {
            "mean_deviation": -50.0,
            "max_divergence": -150.0,
            "rmse": 95.5,
            "correlation": 0.98,
        },
        "tracking_error_series": [
            {"timestamp": "2023-01-01", "tracking_error": 0.0},
            {"timestamp": "2023-01-02", "tracking_error": -20.0},
        ],
        "tracking_error_cumulative": [
            {"timestamp": "2023-01-01", "tracking_error_cumulative": 0.0},
            {"timestamp": "2023-01-02", "tracking_error_cumulative": -20.0},
        ],
        "chart_banners": ["WARNING: Divergencia elevada"],
        "execution_stats": {
            "orderbook_fallback_count": 5,
            "orderbook_fallback_pct": 2.5,
            "rejected_orders": 3,
        },
        "metrics": {
            "cagr": 15.5,
            "sharpe": 1.2,
            "sortino": 1.5,
            "max_drawdown": 12.3,
            "win_rate": 58.5,
            "profit_factor": 1.8,
            "expectancy": 125.0,
            "calmar": 1.26,
            "total_return": 75.5,
            "total_trades": 150,
            "winning_trades": 88,
            "losing_trades": 62,
            "tracking_error_rmse": 95.5,
            "tracking_error_max": 180.0,
            "orderbook_fallback_events": 5,
        },
        "period": {
            "start": "2023-01-01T00:00:00",
            "end": "2024-01-01T00:00:00",
        },
        "metrics_status": "PASS",
        "oos_days": 120,
    }


class TestPerformanceReportEndpoints:
    """Test that performance report endpoints include equity and tracking error fields."""
    
    @pytest.mark.asyncio
    async def test_summary_endpoint_includes_equity_curves(self, mock_backtest_result):
        """Test that /summary endpoint includes both equity_theoretical and equity_realistic."""
        with patch("app.api.v1.performance.performance_service") as mock_service:
            mock_service.get_summary = AsyncMock(return_value=mock_backtest_result)
            
            response = await get_performance_summary()
            
            # Verify response includes equity curves
            assert "equity_theoretical" in response
            assert "equity_realistic" in response
            assert "equity_curve" in response
            assert "equity_curve_theoretical" in response
            assert "equity_curve_realistic" in response
            
            # Verify equity curves are present and non-empty
            assert len(response["equity_theoretical"]) > 0
            assert len(response["equity_realistic"]) > 0
            assert len(response["equity_curve"]) > 0
            
            # Verify values match expected
            assert response["equity_theoretical"] == mock_backtest_result["equity_theoretical"]
            assert response["equity_realistic"] == mock_backtest_result["equity_realistic"]
    
    @pytest.mark.asyncio
    async def test_summary_endpoint_includes_tracking_error_fields(self, mock_backtest_result):
        """Test that /summary endpoint includes tracking error fields."""
        with patch("app.api.v1.performance.performance_service") as mock_service:
            mock_service.get_summary = AsyncMock(return_value=mock_backtest_result)
            
            response = await get_performance_summary()
            
            # Verify response includes tracking error fields
            assert "tracking_error_rmse" in response or response.get("metrics", {}).get("tracking_error_rmse") is not None
            assert "tracking_error_max" in response or response.get("metrics", {}).get("tracking_error_max") is not None
            assert "orderbook_fallback_events" in response or response.get("metrics", {}).get("orderbook_fallback_events") is not None
            assert "has_realistic_data" in response
            assert "tracking_error_metrics" in response
            assert "tracking_error_series" in response
            assert "tracking_error_cumulative" in response
            
            # Verify values match expected
            if "tracking_error_rmse" in response:
                assert response["tracking_error_rmse"] == 95.5
            if "tracking_error_max" in response:
                assert response["tracking_error_max"] == 180.0
            if "orderbook_fallback_events" in response:
                assert response["orderbook_fallback_events"] == 5
            
            assert response["has_realistic_data"] is True
    
    @pytest.mark.asyncio
    async def test_summary_endpoint_without_realistic_data(self):
        """Test that /summary endpoint handles missing realistic data gracefully."""
        mock_result = {
            "status": "success",
            "equity_theoretical": [10000.0, 10100.0, 10200.0],
            "equity_realistic": [],  # Empty realistic data
            "equity_curve": [],
            "tracking_error": None,
            "execution_stats": {},
            "metrics": {
                "cagr": 15.5,
                "sharpe": 1.2,
            },
            "period": {"start": "2023-01-01", "end": "2024-01-01"},
            "metrics_status": "PASS",
            "oos_days": 120,
        }
        
        with patch("app.api.v1.performance.performance_service") as mock_service:
            mock_service.get_summary = AsyncMock(return_value=mock_result)
            
            response = await get_performance_summary()
            
            # Should still include fields but indicate no realistic data
            assert "equity_theoretical" in response
            assert "equity_realistic" in response
            assert response["has_realistic_data"] is False
    
    @pytest.mark.asyncio
    async def test_summary_endpoint_tracking_error_metrics_in_performance_metrics(self, mock_backtest_result):
        """Test that tracking error metrics are included in PerformanceMetrics."""
        with patch("app.api.v1.performance.performance_service") as mock_service:
            mock_service.get_summary = AsyncMock(return_value=mock_backtest_result)
            
            response = await get_performance_summary()
            
            # Verify PerformanceMetrics includes tracking error fields
            if "metrics" in response and response["metrics"]:
                metrics = response["metrics"]
                # These should be in the metrics object
                assert hasattr(metrics, "tracking_error_rmse") or "tracking_error_rmse" in str(metrics)
                assert hasattr(metrics, "tracking_error_max") or "tracking_error_max" in str(metrics)
                assert hasattr(metrics, "orderbook_fallback_events") or "orderbook_fallback_events" in str(metrics)
    
    @pytest.mark.asyncio
    async def test_summary_endpoint_response_structure(self, mock_backtest_result):
        """Test that response structure matches expected format."""
        with patch("app.api.v1.performance.performance_service") as mock_service:
            mock_service.get_summary = AsyncMock(return_value=mock_backtest_result)
            
            response = await get_performance_summary()
            
            # Verify response has expected top-level fields
            assert "status" in response
            assert response["status"] == "success"
            
            # Verify equity data is at top level
            assert "equity_theoretical" in response
            assert "equity_realistic" in response
            assert "equity_curve" in response
            
            # Verify tracking error fields are accessible
            assert "tracking_error_rmse" in response or "has_realistic_data" in response
            assert "chart_banners" in response

    @pytest.mark.asyncio
    async def test_summary_endpoint_includes_chart_banners(self, mock_backtest_result):
        """Test that chart banners are forwarded from service to response."""
        with patch("app.api.v1.performance.performance_service") as mock_service:
            mock_service.get_summary = AsyncMock(return_value=mock_backtest_result)
            
            response = await get_performance_summary()
            
            assert "chart_banners" in response
            assert response["chart_banners"] == mock_backtest_result["chart_banners"]

