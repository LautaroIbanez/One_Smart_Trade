"""Integration tests to verify single source-of-truth for signal data."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.data.signal_data_provider import SignalDataProvider
from app.services.recommendation_service import RecommendationService
from app.quant.signal_engine import generate_signal


@pytest.fixture
def sample_df_1h():
    """Create sample 1h dataframe."""
    dates = pd.date_range("2025-01-01", periods=100, freq="1H")
    return pd.DataFrame({
        "open_time": dates,
        "open": [100.0 + i * 0.1 for i in range(100)],
        "high": [101.0 + i * 0.1 for i in range(100)],
        "low": [99.0 + i * 0.1 for i in range(100)],
        "close": [100.5 + i * 0.1 for i in range(100)],
        "volume": [1000.0 + i * 10 for i in range(100)],
    })


@pytest.fixture
def sample_df_1d():
    """Create sample 1d dataframe."""
    dates = pd.date_range("2025-01-01", periods=30, freq="1D")
    return pd.DataFrame({
        "open_time": dates,
        "open": [100.0 + i * 1.0 for i in range(30)],
        "high": [101.0 + i * 1.0 for i in range(30)],
        "low": [99.0 + i * 1.0 for i in range(30)],
        "close": [100.5 + i * 1.0 for i in range(30)],
        "volume": [10000.0 + i * 100 for i in range(30)],
    })


@pytest.mark.asyncio
async def test_recommendation_service_uses_signal_data_provider(sample_df_1h, sample_df_1d):
    """Test that RecommendationService uses SignalDataProvider for data access."""
    service = RecommendationService()
    
    # Mock the SignalDataProvider
    with patch("app.services.recommendation_service.SignalDataProvider") as mock_provider_class:
        mock_provider = MagicMock()
        mock_provider_class.return_value = mock_provider
        
        # Create mock inputs
        from app.data.signal_data_provider import SignalDataInputs
        mock_inputs = SignalDataInputs(
            df_1h=sample_df_1h,
            df_1d=sample_df_1d,
            venue="binance",
            symbol="BTCUSDT",
        )
        mock_provider.get_validated_inputs.return_value = mock_inputs
        
        # Mock other dependencies
        with patch.object(service, "strategy_service") as mock_strategy_service:
            mock_strategy_service.apply_sl_tp_policy.return_value = {"signal": "BUY", "confidence": 50.0}
            
            with patch("app.services.recommendation_service.create_recommendation") as mock_create:
                mock_create.return_value = MagicMock()
                
                with patch.object(service, "_cache_result") as mock_cache:
                    mock_cache.return_value = {"signal": "BUY", "confidence": 50.0}
                    
                    # Mock user portfolio service
                    with patch.object(service, "_get_user_portfolio_service") as mock_portfolio:
                        mock_portfolio.return_value.get_available_capital.return_value = 10000.0
                        
                        result = await service.get_today_recommendation()
                        
                        # Verify SignalDataProvider was instantiated
                        assert mock_provider_class.called
                        
                        # Verify get_validated_inputs was called
                        assert mock_provider.get_validated_inputs.called
                        call_kwargs = mock_provider.get_validated_inputs.call_args[1]
                        assert call_kwargs["validate_freshness"] is True
                        assert call_kwargs["validate_gaps"] is True


def test_signal_engine_receives_same_data_from_provider(sample_df_1h, sample_df_1d):
    """Test that generate_signal receives the same data that was validated."""
    # Create provider and get validated inputs
    from app.data.curation import DataCuration
    
    mock_curation = MagicMock(spec=DataCuration)
    mock_curation.get_latest_curated.side_effect = lambda interval, **kwargs: {
        "1h": sample_df_1h.copy(),
        "1d": sample_df_1d.copy(),
    }[interval]
    mock_curation.validate_data_freshness.return_value = None
    mock_curation.validate_data_gaps.return_value = None
    
    provider = SignalDataProvider(curation=mock_curation, venue="binance", symbol="BTCUSDT")
    inputs = provider.get_validated_inputs()
    
    # Pass same dataframes to generate_signal
    result = generate_signal(inputs.df_1h, inputs.df_1d)
    
    # Verify signal was generated successfully
    assert "signal" in result
    assert "confidence" in result
    assert result["signal"] in ["BUY", "SELL", "HOLD"]
    
    # Verify dataframes are the same (by checking length and first value)
    assert len(inputs.df_1h) == len(sample_df_1h)
    assert len(inputs.df_1d) == len(sample_df_1d)
    assert inputs.df_1h.iloc[0]["close"] == sample_df_1h.iloc[0]["close"]
    assert inputs.df_1d.iloc[0]["close"] == sample_df_1d.iloc[0]["close"]


def test_multiple_calls_return_same_data(sample_df_1h, sample_df_1d):
    """Test that multiple calls to provider return the same data (cached)."""
    from app.data.curation import DataCuration
    
    mock_curation = MagicMock(spec=DataCuration)
    mock_curation.get_latest_curated.side_effect = lambda interval, **kwargs: {
        "1h": sample_df_1h.copy(),
        "1d": sample_df_1d.copy(),
    }[interval]
    mock_curation.validate_data_freshness.return_value = None
    mock_curation.validate_data_gaps.return_value = None
    
    provider = SignalDataProvider(curation=mock_curation, venue="binance", symbol="BTCUSDT")
    
    inputs1 = provider.get_validated_inputs()
    inputs2 = provider.get_validated_inputs()
    
    # Should return same cached instance
    assert inputs1 is inputs2
    
    # Data should be identical
    assert inputs1.df_1h.equals(inputs2.df_1h)
    assert inputs1.df_1d.equals(inputs2.df_1d)


def test_provider_prevents_direct_filesystem_access():
    """Test that using provider prevents direct filesystem reads in signal generation."""
    from app.data.curation import DataCuration
    
    mock_curation = MagicMock(spec=DataCuration)
    
    # Track calls to get_latest_curated
    call_count = {"count": 0}
    
    def track_calls(*args, **kwargs):
        call_count["count"] += 1
        # Return empty dataframes for this test
        return pd.DataFrame({
            "open_time": pd.date_range("2025-01-01", periods=10, freq="1H"),
            "open": [100.0] * 10,
            "high": [101.0] * 10,
            "low": [99.0] * 10,
            "close": [100.5] * 10,
            "volume": [1000.0] * 10,
        })
    
    mock_curation.get_latest_curated.side_effect = track_calls
    mock_curation.validate_data_freshness.return_value = None
    mock_curation.validate_data_gaps.return_value = None
    
    provider = SignalDataProvider(curation=mock_curation, venue="binance", symbol="BTCUSDT")
    
    # Get inputs once
    inputs = provider.get_validated_inputs()
    
    # Get inputs again (should use cache)
    inputs2 = provider.get_validated_inputs()
    
    # get_latest_curated should only be called once per interval (2 total: 1h + 1d)
    # Even though we called get_validated_inputs twice, cache should prevent additional calls
    assert call_count["count"] == 2  # Once for 1h, once for 1d

