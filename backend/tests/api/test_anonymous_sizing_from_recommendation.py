"""API tests for anonymous sizing using explicit capital."""
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _build_fake_recommendation() -> dict:
    return {
        "signal": "BUY",
        "entry_range": {"optimal": 50000.0},
        "stop_loss_take_profit": {"stop_loss": 45000.0},
        "confidence": 80.0,
        "current_price": 50000.0,
        "analysis": "Test recommendation",
        "indicators": {},
        "risk_metrics": {},
        "timestamp": "2024-01-01T00:00:00Z",
    }


def test_anonymous_sizing_from_recommendation_requires_capital_query_param():
    """GET /api/v1/risk/sizing/from-recommendation without capital should fail validation."""
    response = client.get("/api/v1/risk/sizing/from-recommendation")
    # FastAPI validation error
    assert response.status_code == 422


def test_anonymous_sizing_from_recommendation_with_capital_succeeds(monkeypatch):
    """Anonymous caller can compute sizing by providing explicit capital."""

    fake_rec = _build_fake_recommendation()

    # Patch RecommendationService inside risk router to return a fake recommendation
    with patch("app.api.v1.risk.RecommendationService") as MockService:
        service_instance = MockService.return_value
        service_instance.get_today_recommendation = AsyncMock(return_value=fake_rec)

        response = client.get(
            "/api/v1/risk/sizing/from-recommendation",
            params={"capital": 10000.0, "risk_budget_pct": 1.0, "current_drawdown_pct": 0.0},
        )

        assert response.status_code == 200
        data = response.json()
        # Should return a positive position size using the explicit capital
        assert data["units"] > 0
        assert data["parameters"]["capital"] == 10000.0
        assert data["parameters"]["entry"] == fake_rec["entry_range"]["optimal"]
        assert data["parameters"]["stop"] == fake_rec["stop_loss_take_profit"]["stop_loss"]


