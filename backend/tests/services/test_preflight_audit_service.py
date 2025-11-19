"""Tests for PreflightAuditService to verify gap validation works with cache."""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from app.core.exceptions import DataGapError
from app.services.preflight_audit_service import PreflightAuditService


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
async def test_check_data_gaps_executes_after_freshness_check_with_cache(sample_df_1h, sample_df_1d):
    """Test that _check_data_gaps() executes validate_data_gaps() even after _check_data_freshness() caches data."""
    service = PreflightAuditService()
    
    # Track calls to validate_data_gaps
    gap_validation_calls = []
    
    def track_gap_validation(interval, **kwargs):
        gap_validation_calls.append((interval, kwargs))
        # Simulate gaps detected (corrupted parquet scenario)
        raise DataGapError(
            reason="Critical gaps detected",
            interval=interval,
            gaps=[{"missing_candles": 5, "start": "2025-01-01", "end": "2025-01-02"}],
            tolerance_candles=2,
        )
    
    # Mock the curation to track calls
    with patch.object(service.curation, "validate_data_freshness", return_value=None):
        with patch.object(service.curation, "validate_data_gaps", side_effect=track_gap_validation):
            with patch.object(service.curation, "get_latest_curated", side_effect=lambda interval, **kwargs: {
                "1h": sample_df_1h.copy(),
                "1d": sample_df_1d.copy(),
            }[interval]):
                
                # First call: _check_data_freshness (should cache data, but NOT validate gaps)
                freshness_check = await service._check_data_freshness()
                assert freshness_check.passed
                
                # Verify cache exists
                assert service.data_provider._cached_inputs is not None
                
                # Verify validate_data_gaps was NOT called during freshness check
                assert len(gap_validation_calls) == 0
                
                # Second call: _check_data_gaps (should force refresh and execute validate_data_gaps)
                gaps_check = await service._check_data_gaps()
                
                # Verify that validate_data_gaps was called (force_refresh bypasses cache)
                # Should be called for both 1h and 1d intervals
                assert len(gap_validation_calls) >= 1
                
                # Verify the check failed due to gaps
                assert not gaps_check.passed
                assert "Data gap validation failed" in gaps_check.message
                assert gaps_check.details is not None
                assert "gaps" in gaps_check.details


@pytest.mark.asyncio
async def test_check_data_gaps_force_refresh_prevents_cache_bypass(sample_df_1h, sample_df_1d):
    """Test that force_refresh=True ensures gap validation runs even with cached data."""
    service = PreflightAuditService()
    
    gap_validation_call_count = {"count": 0}
    
    def count_gap_validation(interval, **kwargs):
        gap_validation_call_count["count"] += 1
        # Simulate gaps detected (corrupted parquet scenario)
        raise DataGapError(
            reason="Critical gaps detected after cache",
            interval=interval,
            gaps=[{"missing_candles": 10, "start": "2025-01-01", "end": "2025-01-03"}],
            tolerance_candles=2,
        )
    
    with patch.object(service.curation, "validate_data_freshness", return_value=None):
        with patch.object(service.curation, "validate_data_gaps", side_effect=count_gap_validation):
            with patch.object(service.curation, "get_latest_curated", side_effect=lambda interval, **kwargs: {
                "1h": sample_df_1h.copy(),
                "1d": sample_df_1d.copy(),
            }[interval]):
                
                # Call _check_data_freshness first (caches data, doesn't validate gaps)
                await service._check_data_freshness()
                
                # Verify cache exists
                assert service.data_provider._cached_inputs is not None
                
                # Verify validate_data_gaps was NOT called during freshness check
                assert gap_validation_call_count["count"] == 0
                
                # Now call _check_data_gaps - should force refresh and validate gaps
                gaps_check = await service._check_data_gaps()
                
                # Verify validate_data_gaps was called (force_refresh bypasses cache)
                # Should be called for both 1h and 1d intervals
                assert gap_validation_call_count["count"] >= 1
                
                # Check should fail due to gaps
                assert not gaps_check.passed


@pytest.mark.asyncio
async def test_check_data_gaps_detects_corrupted_parquet(sample_df_1h, sample_df_1d):
    """Test that corrupted parquet (with gaps) is detected and blocks signal generation."""
    service = PreflightAuditService()
    
    # Simulate corrupted parquet with critical gaps
    critical_gaps = [
        {"missing_candles": 5, "start": "2025-01-01T00:00:00Z", "end": "2025-01-01T05:00:00Z"},
        {"missing_candles": 3, "start": "2025-01-02T10:00:00Z", "end": "2025-01-02T13:00:00Z"},
    ]
    
    def validate_gaps_with_error(interval, **kwargs):
        raise DataGapError(
            reason=f"Data gaps detected for interval {interval}: 2 gap(s) with 8 total missing candles (tolerance: 2 candles)",
            interval=interval,
            gaps=critical_gaps,
            tolerance_candles=2,
            context_data={
                "venue": "binance",
                "symbol": "BTCUSDT",
                "lookback_days": 30,
                "total_gaps": 2,
                "critical_gaps": 2,
                "total_missing_candles": 8,
            },
        )
    
    with patch.object(service.curation, "validate_data_freshness", return_value=None):
        with patch.object(service.curation, "validate_data_gaps", side_effect=validate_gaps_with_error):
            with patch.object(service.curation, "get_latest_curated", side_effect=lambda interval, **kwargs: {
                "1h": sample_df_1h.copy(),
                "1d": sample_df_1d.copy(),
            }[interval]):
                
                # First call caches data
                await service._check_data_freshness()
                
                # Second call should detect gaps even with cache (force_refresh=True)
                gaps_check = await service._check_data_gaps()
                
                # Verify check failed
                assert not gaps_check.passed
                assert gaps_check.name == "data_gaps"
                assert "Data gap validation failed" in gaps_check.message
                assert gaps_check.details is not None
                assert gaps_check.details["interval"] in ["1h", "1d"]
                assert "gaps" in gaps_check.details
                assert gaps_check.details["tolerance_candles"] == 2
                
                # Verify audit log details are present
                assert "error" in gaps_check.details
                assert "context" in gaps_check.details

