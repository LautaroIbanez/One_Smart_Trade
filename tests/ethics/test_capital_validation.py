"""Tests for capital validation blocking recommendations."""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from uuid import UUID

from app.services.recommendation_service import RecommendationService
from app.core.config import settings


@pytest.fixture
def mock_user_risk_context_no_capital():
    """Mock UserRiskContext with no capital."""
    from app.services.user_risk_profile_service import UserRiskContext
    return UserRiskContext(
        user_id=UUID(settings.DEFAULT_USER_ID),
        equity=None,
        has_data=False,
        current_drawdown_pct=0.0,
        realized_vol=0.0,
        effective_leverage=0.0,
        current_losing_streak=0,
        trades_last_24h=0,
    )


@pytest.fixture
def mock_user_risk_context_zero_capital():
    """Mock UserRiskContext with zero capital."""
    from app.services.user_risk_profile_service import UserRiskContext
    return UserRiskContext(
        user_id=UUID(settings.DEFAULT_USER_ID),
        equity=0.0,
        has_data=True,
        current_drawdown_pct=0.0,
        realized_vol=0.0,
        effective_leverage=0.0,
        current_losing_streak=0,
        trades_last_24h=0,
    )


@pytest.mark.asyncio
async def test_no_signal_generated_without_capital(mock_user_risk_context_no_capital):
    """Test that no signal is generated when user has no capital validated."""
    service = RecommendationService()
    
    with patch.object(service.user_risk_profile_service, 'get_context', return_value=mock_user_risk_context_no_capital):
        with patch.object(service, '_ensure_champion_context', return_value=Mock()):
            result = await service.generate_recommendation()
    
    assert result is not None
    assert result["status"] == "capital_missing"
    assert "capital" in result["reason"].lower() or "validar" in result["reason"].lower()
    assert result.get("requires_capital_input") is True


@pytest.mark.asyncio
async def test_no_signal_generated_with_zero_capital(mock_user_risk_context_zero_capital):
    """Test that no signal is generated when user has zero capital."""
    service = RecommendationService()
    
    with patch.object(service.user_risk_profile_service, 'get_context', return_value=mock_user_risk_context_zero_capital):
        with patch.object(service, '_ensure_champion_context', return_value=Mock()):
            result = await service.generate_recommendation()
    
    assert result is not None
    assert result["status"] == "capital_missing"
    assert result.get("requires_capital_input") is True


@pytest.mark.asyncio
async def test_capital_validation_before_signal_generation():
    """Test that capital validation happens BEFORE signal generation."""
    service = RecommendationService()
    
    mock_ctx = Mock()
    mock_ctx.has_data = False
    mock_ctx.equity = None
    
    generate_signal_called = []
    
    def track_signal_call(*args, **kwargs):
        generate_signal_called.append(True)
        return {"signal": "BUY", "confidence": 0.8}
    
    with patch.object(service.user_risk_profile_service, 'get_context', return_value=mock_ctx):
        with patch.object(service, '_ensure_champion_context', return_value=Mock()):
            with patch.object(service, 'generate_signal', side_effect=track_signal_call):
                result = await service.generate_recommendation()
    
    # Verify generate_signal was NEVER called
    assert len(generate_signal_called) == 0
    assert result["status"] == "capital_missing"


@pytest.mark.asyncio
async def test_audit_record_created_for_capital_block():
    """Test that an audit record is created when blocking for missing capital."""
    service = RecommendationService()
    
    mock_ctx = Mock()
    mock_ctx.has_data = False
    mock_ctx.equity = None
    
    audit_created = []
    
    def track_audit(*args, **kwargs):
        audit_created.append(kwargs)
    
    with patch.object(service.user_risk_profile_service, 'get_context', return_value=mock_ctx):
        with patch.object(service, '_ensure_champion_context', return_value=Mock()):
            with patch('app.services.recommendation_service.create_risk_audit', side_effect=track_audit):
                result = await service.generate_recommendation()
    
    assert len(audit_created) > 0
    audit_call = audit_created[0]
    assert audit_call.get("audit_type") == "capital_missing"
    assert "capital" in audit_call.get("reason", "").lower() or "validar" in audit_call.get("reason", "").lower()


@pytest.mark.asyncio
async def test_alert_sent_for_capital_block():
    """Test that an internal alert is sent when blocking for missing capital."""
    service = RecommendationService()
    
    mock_ctx = Mock()
    mock_ctx.has_data = False
    mock_ctx.equity = None
    
    alert_sent = []
    
    async def track_alert(*args, **kwargs):
        alert_sent.append(kwargs)
    
    with patch.object(service.user_risk_profile_service, 'get_context', return_value=mock_ctx):
        with patch.object(service, '_ensure_champion_context', return_value=Mock()):
            with patch('app.services.risk_block_alert_service.risk_block_alert_service.send_capital_block_alert', side_effect=track_alert):
                result = await service.generate_recommendation()
    
    assert len(alert_sent) > 0
    assert result["status"] == "capital_missing"

