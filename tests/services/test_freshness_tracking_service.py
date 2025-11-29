"""Unit tests for freshness tracking service."""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch

from app.services.freshness_tracking_service import FreshnessTrackingService


class TestFreshnessTrackingService:
    """Test freshness tracking service."""
    
    def test_stale_warning_deduplication_once_per_interval_per_window(self):
        """Test that stale warnings are emitted once per interval per window."""
        tracker = FreshnessTrackingService()
        
        # First call should emit warning
        assert tracker.should_emit_stale_warning("1h", "performance_summary", cooldown_seconds=3600) is True
        
        # Second call within cooldown should not emit
        assert tracker.should_emit_stale_warning("1h", "performance_summary", cooldown_seconds=3600) is False
        
        # Different interval should emit
        assert tracker.should_emit_stale_warning("1d", "performance_summary", cooldown_seconds=3600) is True
        
        # Different window should emit
        assert tracker.should_emit_stale_warning("1h", "market_data", cooldown_seconds=3600) is True
        
        # Same interval/window after cooldown should emit again
        with patch('app.services.freshness_tracking_service.datetime') as mock_dt:
            mock_dt.now.return_value.timestamp.return_value = datetime.now(timezone.utc).timestamp() + 3700  # 1h+100s
            assert tracker.should_emit_stale_warning("1h", "performance_summary", cooldown_seconds=3600) is True
    
    def test_record_no_trades(self):
        """Test recording NO_TRADES events."""
        tracker = FreshnessTrackingService()
        
        tracker.record_no_trades("no_signals_generated")
        tracker.record_no_trades("no_signals_generated")
        tracker.record_no_trades("orders_rejected")
        
        counts = tracker.get_aggregated_counts()
        assert counts["no_trades_by_cause"]["no_signals_generated"] == 2
        assert counts["no_trades_by_cause"]["orders_rejected"] == 1
        assert counts["total_no_trades"] == 3
    
    def test_record_ingestion(self):
        """Test recording ingestion times."""
        tracker = FreshnessTrackingService()
        
        timestamp = "2025-01-15T12:00:00Z"
        tracker.record_ingestion("1h", timestamp)
        tracker.record_ingestion("1d", timestamp)
        
        status = tracker.get_freshness_status(["1h", "1d"])
        # Note: last_ingestion_times is stored internally, not in get_freshness_status
        # This test verifies the method doesn't raise
        assert "intervals" in status
    
    @patch('app.services.freshness_tracking_service.DataCuration')
    @patch('app.services.freshness_tracking_service.SignalDataProvider')
    def test_get_freshness_status(self, mock_provider_class, mock_curation_class):
        """Test getting freshness status."""
        tracker = FreshnessTrackingService()
        
        # Mock curation and provider
        mock_curation = Mock()
        mock_curation.get_curated_metadata.return_value = {
            "generated_at": "2025-01-15T12:00:00Z",
        }
        tracker.curation = mock_curation
        
        mock_provider = Mock()
        mock_provider.describe_dataset_freshness.return_value = {
            "intervals": {
                "1h": {
                    "status": "ok",
                    "latest_open_time": (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(),
                    "age_minutes": 30.0,
                },
                "1d": {
                    "status": "ok",
                    "latest_open_time": (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat(),
                    "age_minutes": 1500.0,  # Stale (> 48h threshold)
                },
            },
        }
        tracker.signal_data_provider = mock_provider
        
        status = tracker.get_freshness_status(["1h", "1d"])
        
        assert "intervals" in status
        assert "1h" in status["intervals"]
        assert "1d" in status["intervals"]
        assert status["intervals"]["1h"]["is_stale"] is False
        assert status["intervals"]["1d"]["is_stale"] is True
        assert "stale_counts" in status
        assert "no_trades_counts" in status
    
    def test_get_aggregated_counts(self):
        """Test getting aggregated counts."""
        tracker = FreshnessTrackingService()
        
        tracker.record_no_trades("no_signals_generated")
        tracker.record_no_trades("orders_rejected")
        
        # Trigger some stale warnings
        tracker.should_emit_stale_warning("1h", "test_window")
        tracker.should_emit_stale_warning("1d", "test_window")
        
        counts = tracker.get_aggregated_counts()
        
        assert "no_trades_by_cause" in counts
        assert "total_no_trades" in counts
        assert counts["total_no_trades"] == 2
        assert "stale_warnings_emitted" in counts
        assert counts["stale_warnings_emitted"]["1h"] == 1
        assert counts["stale_warnings_emitted"]["1d"] == 1

