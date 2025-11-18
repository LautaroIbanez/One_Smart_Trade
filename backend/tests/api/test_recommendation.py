from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.v1 import recommendation as recommendation_module

client = TestClient(app)


@pytest.fixture
def sample_recommendation() -> dict:
    return {
        "signal": "BUY",
        "entry_range": {"min": 10000.0, "max": 10200.0, "optimal": 10100.0},
        "stop_loss_take_profit": {
            "stop_loss": 9900.0,
            "take_profit": 10500.0,
            "stop_loss_pct": -2.0,
            "take_profit_pct": 4.0,
        },
        "confidence": 62.5,
        "confidence_raw": 62.5,
        "confidence_calibrated": 64.2,
        "confidence_band": {"lower": 61.2, "upper": 66.8, "source": "platt"},
        "current_price": 10150.0,
        "analysis": "Confianza heurística y calibrada disponibles.",
        "indicators": {},
        "risk_metrics": {},
        "factors": {},
        "signal_breakdown": {},
        "calibration_metadata": {"regime": "balanced", "ece": 0.03, "calibrator_type": "platt"},
        "timestamp": "2025-11-17T00:00:00Z",
        "status": "closed",
        "opened_at": "2025-11-17T00:00:00Z",
        "closed_at": "2025-11-17T12:00:00Z",
        "exit_reason": "take_profit",
        "exit_price": 10500.0,
        "exit_price_pct": 4.0,
        "disclaimer": "Mock",
        "recommended_risk_fraction": 0.01,
    }


def test_today_recommendation_includes_confidence_fields(monkeypatch, sample_recommendation):
    async def fake_get_today_recommendation():
        return sample_recommendation

    monkeypatch.setattr(
        recommendation_module.recommendation_service,
        "get_today_recommendation",
        fake_get_today_recommendation,
    )

    response = client.get("/api/v1/recommendation/today")
    assert response.status_code == 200
    data = response.json()

    assert data["confidence_raw"] == pytest.approx(sample_recommendation["confidence_raw"])
    assert data["confidence_calibrated"] == pytest.approx(sample_recommendation["confidence_calibrated"])
    assert "confidence_band" in data and data["confidence_band"]["lower"] < data["confidence_band"]["upper"]
    assert "analysis" in data and "Confianza" in data["analysis"]


def test_today_recommendation_includes_backtest_metrics(monkeypatch, sample_recommendation):
    """Test that backtest metrics are included in /today endpoint response."""
    sample_recommendation.update({
        "backtest_run_id": "test-run-123",
        "backtest_cagr": 15.5,
        "backtest_win_rate": 65.0,
        "backtest_risk_reward_ratio": 1.8,
        "backtest_max_drawdown": 12.3,
        "backtest_slippage_bps": 5.0,
    })

    async def fake_get_today_recommendation():
        return sample_recommendation

    monkeypatch.setattr(
        recommendation_module.recommendation_service,
        "get_today_recommendation",
        fake_get_today_recommendation,
    )

    response = client.get("/api/v1/recommendation/today")
    assert response.status_code == 200
    data = response.json()

    assert data["backtest_run_id"] == "test-run-123"
    assert data["backtest_cagr"] == pytest.approx(15.5)
    assert data["backtest_win_rate"] == pytest.approx(65.0)
    assert data["backtest_risk_reward_ratio"] == pytest.approx(1.8)
    assert data["backtest_max_drawdown"] == pytest.approx(12.3)
    assert data["backtest_slippage_bps"] == pytest.approx(5.0)


def test_today_recommendation_includes_execution_plan(monkeypatch, sample_recommendation):
    """Test that execution plan is included in /today endpoint response."""
    sample_recommendation.update({
        "execution_plan": {
            "operational_window": {
                "optimal_start": "2025-11-17T12:00:00+00:00",
                "optimal_end": "2025-11-17T16:00:00+00:00",
                "acceptable_end": "2025-11-18T12:00:00+00:00",
                "timezone": "UTC",
                "description": "Óptima: 12:00 - 16:00 UTC, Aceptable: hasta 12:00 UTC",
            },
            "order_type": "limit",
            "suggested_size": {
                "units": 0.05,
                "notional_usd": 505.0,
                "risk_amount_usd": 10.0,
                "risk_pct": 1.0,
                "capital_used": 1000.0,
                "sizing_method": "risk_based",
            },
            "instructions": "1. Verifica la señal: COMPRA\n2. Precio actual: $10,150.00",
            "minimum_capital_required": 1000.0,
            "risk_per_trade_pct": 1.0,
            "notes": [],
        },
    })

    async def fake_get_today_recommendation():
        return sample_recommendation

    monkeypatch.setattr(
        recommendation_module.recommendation_service,
        "get_today_recommendation",
        fake_get_today_recommendation,
    )

    response = client.get("/api/v1/recommendation/today")
    assert response.status_code == 200
    data = response.json()

    assert "execution_plan" in data
    plan = data["execution_plan"]
    assert plan["order_type"] == "limit"
    assert "operational_window" in plan
    assert "suggested_size" in plan
    assert "instructions" in plan
    assert "minimum_capital_required" in plan
    assert plan["operational_window"]["timezone"] == "UTC"
    assert "optimal_start" in plan["operational_window"]
    assert "optimal_end" in plan["operational_window"]
    assert "acceptable_end" in plan["operational_window"]


def test_history_endpoint_includes_backtest_metrics(monkeypatch):
    """Test that backtest metrics are included in /history endpoint response."""
    sample_item = {
        "id": 1,
        "timestamp": "2025-11-17T00:00:00Z",
        "date": "2025-11-17",
        "signal": "BUY",
        "status": "closed",
        "execution_status": "TP",
        "backtest_run_id": "test-run-456",
        "backtest_cagr": 20.0,
        "backtest_win_rate": 70.0,
        "backtest_risk_reward_ratio": 2.0,
        "backtest_max_drawdown": 10.0,
        "backtest_slippage_bps": 4.5,
    }

    async def fake_history(**kwargs):
        return {
            "items": [sample_item],
            "next_cursor": None,
            "has_more": False,
            "filters": kwargs,
            "insights": {"sparkline_series": {}, "stats": {}},
            "download_url": "/api/v1/recommendation/history?format=csv",
        }

    monkeypatch.setattr(
        recommendation_module.recommendation_service,
        "get_recommendation_history",
        fake_history,
    )

    response = client.get("/api/v1/recommendation/history")
    assert response.status_code == 200
    data = response.json()

    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["backtest_run_id"] == "test-run-456"
    assert item["backtest_cagr"] == pytest.approx(20.0)
    assert item["backtest_win_rate"] == pytest.approx(70.0)
    assert item["backtest_risk_reward_ratio"] == pytest.approx(2.0)
    assert item["backtest_max_drawdown"] == pytest.approx(10.0)
    assert item["backtest_slippage_bps"] == pytest.approx(4.5)


def test_history_endpoint_passes_filters(monkeypatch):
    captured: dict[str, Any] = {}

    async def fake_history(**kwargs):
        captured.update(kwargs)
        return {
            "items": [],
            "next_cursor": None,
            "has_more": False,
            "filters": kwargs,
            "insights": {"sparkline_series": {}, "stats": {}},
            "download_url": "/api/v1/recommendation/history?format=csv",
        }

    monkeypatch.setattr(
        recommendation_module.recommendation_service,
        "get_recommendation_history",
        fake_history,
    )

    response = client.get(
        "/api/v1/recommendation/history",
        params={
            "limit": 30,
            "signal": "BUY",
            "result": "TP",
            "status": "closed",
            "tracking_error_min": 1.0,
            "tracking_error_max": 5.0,
        },
    )

    assert response.status_code == 200
    assert captured["limit"] == 30
    assert captured["signal"] == "BUY"
    assert captured["result"] == "TP"
    assert captured["status"] == "closed"
    assert captured["tracking_error_min"] == 1.0
    assert captured["tracking_error_max"] == 5.0
    data = response.json()
    assert "items" in data and isinstance(data["items"], list)
    assert "download_url" in data


def test_history_endpoint_export(monkeypatch):
    async def fake_export(**kwargs):
        return {
            "content": b"timestamp,signal\n",
            "media_type": "text/csv",
            "headers": {"Content-Disposition": 'attachment; filename="test.csv"'},
        }

    monkeypatch.setattr(
        recommendation_module.recommendation_service,
        "export_recommendation_history",
        fake_export,
    )

    response = client.get("/api/v1/recommendation/history?format=csv")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv"
    assert "attachment" in response.headers.get("content-disposition", "").lower()


def test_history_endpoint_cursor_pagination(monkeypatch):
    """Test cursor-based pagination."""
    captured: dict[str, Any] = {}

    async def fake_history(**kwargs):
        captured.update(kwargs)
        cursor = kwargs.get("cursor")
        has_more = cursor is None  # First page has more
        next_cursor = "dGVzdF9jdXJzb3I=" if has_more else None
        return {
            "items": [{"id": 1, "timestamp": "2023-01-01T00:00:00Z", "signal": "BUY"}],
            "next_cursor": next_cursor,
            "has_more": has_more,
            "filters": kwargs,
            "insights": {"sparkline_series": {}, "stats": {}},
            "download_url": None,
        }

    monkeypatch.setattr(
        recommendation_module.recommendation_service,
        "get_recommendation_history",
        fake_history,
    )

    # First page
    response = client.get("/api/v1/recommendation/history", params={"limit": 25})
    assert response.status_code == 200
    data = response.json()
    assert "next_cursor" in data
    assert data["has_more"] is True
    assert len(data["items"]) == 1

    # Second page with cursor
    cursor = data["next_cursor"]
    response = client.get("/api/v1/recommendation/history", params={"limit": 25, "cursor": cursor})
    assert response.status_code == 200
    data2 = response.json()
    assert captured["cursor"] == cursor
    assert data2["has_more"] is False


def test_history_endpoint_date_filters(monkeypatch):
    """Test date range filters."""
    captured: dict[str, Any] = {}

    async def fake_history(**kwargs):
        captured.update(kwargs)
        return {
            "items": [],
            "next_cursor": None,
            "has_more": False,
            "filters": kwargs,
            "insights": {"sparkline_series": {}, "stats": {}},
            "download_url": None,
        }

    monkeypatch.setattr(
        recommendation_module.recommendation_service,
        "get_recommendation_history",
        fake_history,
    )

    response = client.get(
        "/api/v1/recommendation/history",
        params={"start_date": "2023-01-01", "end_date": "2023-12-31"},
    )
    assert response.status_code == 200
    assert captured["start_date"] == "2023-01-01"
    assert captured["end_date"] == "2023-12-31"


def test_history_endpoint_csv_export_with_filters(monkeypatch):
    """Test CSV export includes all filters."""
    captured: dict[str, Any] = {}

    async def fake_export(**kwargs):
        captured.update(kwargs)
        return {
            "content": b"timestamp,date,signal,tracking_error_pct\n2023-01-01T00:00:00Z,2023-01-01,BUY,1.5\n",
            "media_type": "text/csv",
            "headers": {
                "Content-Disposition": 'attachment; filename="test.csv"',
                "X-Records": "1",
            },
        }

    monkeypatch.setattr(
        recommendation_module.recommendation_service,
        "export_recommendation_history",
        fake_export,
    )

    response = client.get(
        "/api/v1/recommendation/history",
        params={
            "format": "csv",
            "signal": "BUY",
            "tracking_error_min": 1.0,
            "tracking_error_max": 5.0,
            "start_date": "2023-01-01",
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv"
    assert captured["signal"] == "BUY"
    assert captured["tracking_error_min"] == 1.0
    assert captured["tracking_error_max"] == 5.0
    assert captured["start_date"] == "2023-01-01"
    assert "X-Records" in response.headers


def test_history_endpoint_limit_validation(monkeypatch):
    """Test limit parameter validation."""
    async def fake_history(**kwargs):
        return {
            "items": [],
            "next_cursor": None,
            "has_more": False,
            "filters": kwargs,
            "insights": {"sparkline_series": {}, "stats": {}},
            "download_url": None,
        }

    monkeypatch.setattr(
        recommendation_module.recommendation_service,
        "get_recommendation_history",
        fake_history,
    )

    # Test limit too high
    response = client.get("/api/v1/recommendation/history", params={"limit": 300})
    assert response.status_code == 422  # Validation error

    # Test limit too low
    response = client.get("/api/v1/recommendation/history", params={"limit": 0})
    assert response.status_code == 422

    # Test valid limit
    response = client.get("/api/v1/recommendation/history", params={"limit": 50})
    assert response.status_code == 200


def test_today_recommendation_rejects_stale_data(monkeypatch):
    """Test that recommendation generation is blocked when data is stale."""
    async def fake_get_today_recommendation():
        # Simulate stale data response from service
        return {
            "status": "data_stale",
            "reason": "Data stale for interval 1d: latest candle is 120.0 minutes old (threshold: 90 minutes)",
            "interval": "1d",
            "latest_timestamp": "2025-01-01T10:00:00Z",
            "threshold_minutes": 90,
        }
    
    # Mock the service to return stale data status
    monkeypatch.setattr(
        recommendation_module.recommendation_service,
        "get_today_recommendation",
        fake_get_today_recommendation,
    )
    
    response = client.get("/api/v1/recommendation/today")
    # The endpoint should return 503 Service Unavailable for stale data
    assert response.status_code == 503
    data = response.json()
    assert data["detail"]["status"] == "data_stale"
    assert "stale" in data["detail"]["reason"].lower()
    assert data["detail"]["interval"] == "1d"
    assert data["detail"]["threshold_minutes"] == 90


def test_today_recommendation_rejects_data_gaps(monkeypatch):
    """Test that recommendation generation is blocked when data has gaps."""
    async def fake_get_today_recommendation():
        # Simulate data gaps response from service
        return {
            "status": "data_gaps",
            "reason": "Data gaps detected for interval 1d: 1 gap(s) with 3 total missing candles (tolerance: 2 candles)",
            "interval": "1d",
            "gaps": [
                {
                    "status": "gap",
                    "interval": "1d",
                    "start": "2025-01-10T00:00:00Z",
                    "end": "2025-01-13T00:00:00Z",
                    "missing_candles": 3,
                }
            ],
            "tolerance_candles": 2,
        }
    
    # Mock the service to return data gaps status
    monkeypatch.setattr(
        recommendation_module.recommendation_service,
        "get_today_recommendation",
        fake_get_today_recommendation,
    )
    
    response = client.get("/api/v1/recommendation/today")
    # The endpoint should return 503 Service Unavailable for data gaps
    assert response.status_code == 503
    data = response.json()
    assert data["detail"]["status"] == "data_gaps"
    assert "gaps" in data["detail"]["reason"].lower()
    assert data["detail"]["interval"] == "1d"
    assert data["detail"]["tolerance_candles"] == 2
    assert len(data["detail"]["gaps"]) == 1
    assert data["detail"]["gaps"][0]["missing_candles"] == 3