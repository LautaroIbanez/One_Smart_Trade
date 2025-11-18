"""Tests for daily risk limit validation."""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta
from uuid import UUID

from app.services.recommendation_service import RecommendationService
from app.core.config import settings


@pytest.fixture
def mock_user_risk_context_with_capital():
    """Mock UserRiskContext with valid capital."""
    from app.services.user_risk_profile_service import UserRiskContext
    return UserRiskContext(
        user_id=UUID(settings.DEFAULT_USER_ID),
        equity=10000.0,
        has_data=True,
        current_drawdown_pct=0.0,
        realized_vol=0.0,
        effective_leverage=1.0,
        current_losing_streak=0,
        trades_last_24h=0,
    )


@pytest.fixture
def mock_activity_summary_7_trades():
    """Mock TradeActivitySummary with 7 trades (at preventive limit)."""
    from app.services.trade_activity_ledger import TradeActivitySummary
    return TradeActivitySummary(
        user_id=settings.DEFAULT_USER_ID,
        trades_count=7,
        trades_remaining=0,
        max_trades_24h=8,
        is_at_limit=False,  # Not at limit yet, but at preventive limit
        committed_risk_pct=2.5,
        committed_risk_amount=250.0,
        daily_risk_limit_pct=3.0,
        daily_risk_warning_pct=2.0,
    )


@pytest.mark.asyncio
async def test_preventive_limit_blocks_trade_8(mock_user_risk_context_with_capital, mock_activity_summary_7_trades):
    """Test that preventive limit (7 trades) blocks trade #8."""
    service = RecommendationService()
    
    with patch.object(service.user_risk_profile_service, 'get_context', return_value=mock_user_risk_context_with_capital):
        with patch.object(service, '_ensure_champion_context', return_value=Mock()):
            with patch.object(service.trade_activity_ledger, 'get_activity_summary', return_value=mock_activity_summary_7_trades):
                with patch.object(service.trade_activity_ledger, 'can_trade', return_value=(False, "Límite preventivo alcanzado")):
                    result = await service.generate_recommendation()
    
    assert result is not None
    assert result["status"] == "trade_limit_preventive"
    assert result.get("trades_count") == 7
    assert result.get("max_trades_24h") == 8


@pytest.mark.asyncio
async def test_3_percent_daily_risk_blocks_trade():
    """Test that 3% daily risk limit blocks new trades."""
    service = RecommendationService()
    
    mock_ctx = mock_user_risk_context_with_capital
    mock_activity = Mock()
    mock_activity.trades_count = 3
    mock_activity.trades_remaining = 5
    mock_activity.max_trades_24h = 8
    mock_activity.is_at_limit = False
    mock_activity.committed_risk_pct = 2.8  # Already at 2.8%
    mock_activity.committed_risk_amount = 280.0
    
    # Mock sizing result that would push over 3%
    mock_sizing = {
        "risk_amount": 50.0,  # This would push total to 3.3%
        "risk_pct": 0.5,
        "units": 1.0,
    }
    
    with patch.object(service.user_risk_profile_service, 'get_context', return_value=mock_ctx):
        with patch.object(service, '_ensure_champion_context', return_value=Mock()):
            with patch.object(service.trade_activity_ledger, 'get_activity_summary', return_value=mock_activity):
                with patch.object(service.trade_activity_ledger, 'can_trade', return_value=(True, None)):
                    with patch.object(service, '_calculate_position_sizing', return_value=mock_sizing):
                        result = await service.generate_recommendation()
    
    # Should be blocked by daily risk limit
    assert result is not None
    assert result["status"] == "daily_risk_limit_exceeded"
    assert result.get("daily_limit_pct") == 3.0
    assert result.get("total_risk_pct", 0) >= 3.0


@pytest.mark.asyncio
async def test_2_percent_warning_does_not_block():
    """Test that 2% warning threshold does not block trades, only warns."""
    service = RecommendationService()
    
    mock_ctx = mock_user_risk_context_with_capital
    mock_activity = Mock()
    mock_activity.trades_count = 2
    mock_activity.trades_remaining = 6
    mock_activity.max_trades_24h = 8
    mock_activity.is_at_limit = False
    mock_activity.committed_risk_pct = 1.8  # Already at 1.8%
    mock_activity.committed_risk_amount = 180.0
    
    # Mock sizing result that would push to 2.1% (warning but not blocked)
    mock_sizing = {
        "risk_amount": 30.0,  # This would push total to 2.1%
        "risk_pct": 0.3,
        "units": 1.0,
    }
    
    generate_signal_called = []
    
    def track_signal(*args, **kwargs):
        generate_signal_called.append(True)
        return {"signal": "BUY", "confidence": 0.8}
    
    with patch.object(service.user_risk_profile_service, 'get_context', return_value=mock_ctx):
        with patch.object(service, '_ensure_champion_context', return_value=Mock()):
            with patch.object(service.trade_activity_ledger, 'get_activity_summary', return_value=mock_activity):
                with patch.object(service.trade_activity_ledger, 'can_trade', return_value=(True, None)):
                    with patch.object(service, '_calculate_position_sizing', return_value=mock_sizing):
                        with patch.object(service, 'generate_signal', side_effect=track_signal):
                            result = await service.generate_recommendation()
    
    # Should NOT be blocked (only warned)
    assert result is not None
    assert result["status"] != "daily_risk_limit_exceeded"
    # Should have warnings
    assert "warnings" in result or result.get("status") == "ok"


@pytest.mark.asyncio
async def test_audit_record_created_for_daily_risk_block():
    """Test that an audit record is created when blocking for daily risk limit."""
    service = RecommendationService()
    
    mock_ctx = mock_user_risk_context_with_capital
    mock_activity = Mock()
    mock_activity.trades_count = 3
    mock_activity.committed_risk_pct = 2.8
    mock_activity.committed_risk_amount = 280.0
    
    mock_sizing = {
        "risk_amount": 50.0,
        "risk_pct": 0.5,
    }
    
    audit_created = []
    
    def track_audit(*args, **kwargs):
        audit_created.append(kwargs)
    
    with patch.object(service.user_risk_profile_service, 'get_context', return_value=mock_ctx):
        with patch.object(service, '_ensure_champion_context', return_value=Mock()):
            with patch.object(service.trade_activity_ledger, 'get_activity_summary', return_value=mock_activity):
                with patch.object(service.trade_activity_ledger, 'can_trade', return_value=(True, None)):
                    with patch.object(service, '_calculate_position_sizing', return_value=mock_sizing):
                        with patch('app.services.recommendation_service.create_risk_audit', side_effect=track_audit):
                            result = await service.generate_recommendation()
    
    assert len(audit_created) > 0
    audit_call = audit_created[0]
    assert audit_call.get("audit_type") == "daily_risk_limit_exceeded"
    assert "3%" in audit_call.get("reason", "") or "riesgo diario" in audit_call.get("reason", "").lower()


@pytest.mark.asyncio
async def test_alert_sent_for_daily_risk_block():
    """Test that an internal alert is sent when blocking for daily risk limit."""
    service = RecommendationService()
    
    mock_ctx = mock_user_risk_context_with_capital
    mock_activity = Mock()
    mock_activity.trades_count = 3
    mock_activity.committed_risk_pct = 2.8
    mock_activity.committed_risk_amount = 280.0
    
    mock_sizing = {
        "risk_amount": 50.0,
        "risk_pct": 0.5,
    }
    
    alert_sent = []
    
    async def track_alert(*args, **kwargs):
        alert_sent.append(kwargs)
    
    with patch.object(service.user_risk_profile_service, 'get_context', return_value=mock_ctx):
        with patch.object(service, '_ensure_champion_context', return_value=Mock()):
            with patch.object(service.trade_activity_ledger, 'get_activity_summary', return_value=mock_activity):
                with patch.object(service.trade_activity_ledger, 'can_trade', return_value=(True, None)):
                    with patch.object(service, '_calculate_position_sizing', return_value=mock_sizing):
                        with patch('app.services.risk_block_alert_service.risk_block_alert_service.send_daily_risk_limit_alert', side_effect=track_alert):
                            result = await service.generate_recommendation()
    
    assert len(alert_sent) > 0
    assert result["status"] == "daily_risk_limit_exceeded"

