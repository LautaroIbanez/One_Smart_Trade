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
