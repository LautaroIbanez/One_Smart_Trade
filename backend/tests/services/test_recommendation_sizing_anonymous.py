"""Tests for anonymous/portfolio-less sizing behavior in RecommendationService."""
from types import SimpleNamespace

from app.services.recommendation_service import RecommendationService


def test_calculate_position_sizing_missing_equity_returns_structured_hint(monkeypatch):
    """When user has no equity data, _calculate_position_sizing should return a structured missing_equity payload."""
    service = RecommendationService()

    # Minimal recommendation with entry/stop so sizing path is exercised
    recommendation = {
        "entry_range": {"optimal": 50000.0},
        "stop_loss_take_profit": {"stop_loss": 45000.0},
        "signal": "BUY",
        "symbol": "BTCUSDT",
    }

    # Fake risk context with no equity data
    fake_ctx = SimpleNamespace(
        has_data=False,
        equity=0.0,
        peak_equity=None,
        drawdown_pct=0.0,
        risk_capacity=1.0,
        base_risk_pct=1.0,
        realized_vol=None,
        win_rate=None,
        payoff_ratio=None,
        trade_history=[],
    )

    def fake_get_context(user_id, base_risk_pct=1.0):  # noqa: ARG001
        return fake_ctx

    monkeypatch.setattr(service.user_risk_profile_service, "get_context", fake_get_context)

    sizing = service._calculate_position_sizing(recommendation, user_id=None)

    assert isinstance(sizing, dict)
    assert sizing.get("status") == "missing_equity"
    assert sizing.get("requires_capital_input") is True
    hint = sizing.get("capital_input_hint") or {}
    endpoints = hint.get("endpoints") or []
    assert "/api/v1/risk/sizing" in endpoints
    assert "/api/v1/risk/sizing/from-recommendation" in endpoints


