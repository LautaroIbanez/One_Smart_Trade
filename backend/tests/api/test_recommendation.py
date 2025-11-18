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
