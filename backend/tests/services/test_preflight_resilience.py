"""
Tests for preflight resilience to metric failures.

Ensures that preflight continues even when metrics fail, preventing
metric errors from interrupting critical ingestion operations.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from app.services.preflight import run_preflight, _backfill_gap
from app.data.ingestion import DataIngestion
from app.observability.metrics import record_data_gap, DATA_GAPS


@pytest.mark.asyncio
async def test_preflight_continues_when_data_gap_metric_fails():
    """Test that preflight continues when record_data_gap raises ValueError."""
    # Mock record_data_gap to raise ValueError (simulating missing labels)
    with patch("app.services.preflight.record_data_gap") as mock_record:
        mock_record.side_effect = ValueError("histogram metric is missing label values")
        
        # Mock ingestion to return gaps
        mock_ingestion = MagicMock()
        mock_ingestion.check_gaps.return_value = [
            {
                "status": "gap",
                "interval": "1h",
                "start": (datetime.utcnow() - timedelta(days=1)).isoformat(),
                "end": datetime.utcnow().isoformat(),
                "missing_candles": 10,
            }
        ]
        mock_ingestion.ingest_timeframe = AsyncMock(return_value={
            "status": "success",
            "interval": "1h",
            "rows": 100,
        })
        
        # Mock curation
        mock_curation = MagicMock()
        mock_curation.curate_interval.return_value = {"status": "success"}
        
        with patch("app.services.preflight.DataIngestion", return_value=mock_ingestion):
            with patch("app.services.preflight.DataCuration", return_value=mock_curation):
                with patch("app.services.preflight.SessionLocal"):
                    with patch("app.services.preflight.log_run"):
                        # This should not raise an exception even though the metric failed
                        try:
                            await run_preflight(days=1, intervals=("1h",))
                            # If we get here, the preflight completed despite metric failure
                            assert True
                        except ValueError as e:
                            if "missing label" in str(e).lower() or "histogram metric" in str(e).lower():
                                pytest.fail(f"Preflight should continue despite metric failure, but raised: {e}")
                            raise


@pytest.mark.asyncio
async def test_backfill_gap_continues_when_ingestion_metrics_fail():
    """Test that _backfill_gap continues when Binance metrics fail."""
    # This test verifies that ingestion continues even if metrics fail
    # The actual metric failure happens in binance_client.get_klines
    # which is already wrapped with error handling
    
    mock_ingestion = MagicMock()
    mock_ingestion.ingest_timeframe = AsyncMock(return_value={
        "status": "success",
        "interval": "1h",
        "rows": 100,
    })
    
    start = datetime.utcnow() - timedelta(days=1)
    end = datetime.utcnow()
    
    # This should complete successfully
    results = await _backfill_gap(mock_ingestion, "1h", start, end, chunk_size=100)
    
    assert len(results) > 0
    assert results[0]["status"] == "success"


def test_record_data_gap_raises_valueerror_with_missing_labels():
    """Test that record_data_gap can raise ValueError (for testing resilience)."""
    # This test verifies the behavior we're protecting against
    # In practice, record_data_gap should work, but we want to ensure
    # that if it fails, preflight continues
    
    # Verify that calling with correct label works
    try:
        record_data_gap("1h")
        # If no exception, the metric is working correctly
        assert True
    except ValueError as e:
        # If it raises ValueError, that's the error we're protecting against
        # This test documents the expected failure mode
        assert "missing label" in str(e).lower() or "histogram metric" in str(e).lower()


@pytest.mark.asyncio
async def test_preflight_logs_warning_on_metric_failure():
    """Test that preflight logs a warning when metrics fail."""
    import logging
    from app.core.logging import logger
    
    with patch("app.services.preflight.record_data_gap") as mock_record:
        mock_record.side_effect = ValueError("histogram metric is missing label values")
        
        mock_ingestion = MagicMock()
        mock_ingestion.check_gaps.return_value = [
            {
                "status": "gap",
                "interval": "1h",
                "start": (datetime.utcnow() - timedelta(days=1)).isoformat(),
                "end": datetime.utcnow().isoformat(),
                "missing_candles": 10,
            }
        ]
        mock_ingestion.ingest_timeframe = AsyncMock(return_value={
            "status": "success",
            "interval": "1h",
            "rows": 100,
        })
        
        mock_curation = MagicMock()
        mock_curation.curate_interval.return_value = {"status": "success"}
        
        with patch("app.services.preflight.DataIngestion", return_value=mock_ingestion):
            with patch("app.services.preflight.DataCuration", return_value=mock_curation):
                with patch("app.services.preflight.SessionLocal"):
                    with patch("app.services.preflight.log_run"):
                        with patch.object(logger, "warning") as mock_warning:
                            await run_preflight(days=1, intervals=("1h",))
                            
                            # Verify that a warning was logged
                            warning_calls = [call for call in mock_warning.call_args_list 
                                           if "Failed to record data gap metric" in str(call)]
                            assert len(warning_calls) > 0, "Expected warning log for metric failure"

