"""Service to track data freshness and NO_TRADES counts for observability."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from app.core.logging import logger
from app.data.curation import DataCuration
from app.data.signal_data_provider import SignalDataProvider


class FreshnessTrackingService:
    """Track data freshness status per interval and aggregate NO_TRADES counts."""
    
    def __init__(self):
        """Initialize freshness tracking service."""
        self.curation = DataCuration()
        self.signal_data_provider = SignalDataProvider()
        # Track stale warnings per interval per window (to deduplicate)
        self._stale_warnings_emitted: dict[str, dict[str, float]] = defaultdict(dict)
        # Track NO_TRADES counts
        self._no_trades_counts: dict[str, int] = defaultdict(int)
        # Track last ingestion times per interval
        self._last_ingestion_times: dict[str, str | None] = {}
    
    def get_freshness_status(self, intervals: list[str] | None = None) -> dict[str, Any]:
        """
        Get freshness status for all intervals.
        
        Args:
            intervals: List of intervals to check (default: ["1h", "1d"])
            
        Returns:
            Dict with freshness status per interval and last ingestion times
        """
        intervals = intervals or ["1h", "1d"]
        status: dict[str, Any] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "intervals": {},
            "last_ingestion_times": {},
            "stale_counts": {},
            "no_trades_counts": dict(self._no_trades_counts),
        }
        
        for interval in intervals:
            try:
                metadata = self.curation.get_curated_metadata(interval, venue="binance", symbol="BTCUSDT")
                freshness = self.signal_data_provider.describe_dataset_freshness([interval])
                
                interval_status = freshness.get("intervals", {}).get(interval, {})
                latest_open_time = interval_status.get("latest_open_time")
                age_minutes = interval_status.get("age_minutes")
                status_code = interval_status.get("status", "unknown")
                
                # Determine if stale based on threshold
                threshold_minutes = 90 if interval == "1h" else 2880  # 90 min for 1h, 48h for 1d
                is_stale = age_minutes is not None and age_minutes > threshold_minutes
                
                status["intervals"][interval] = {
                    "status": "stale" if is_stale else status_code,
                    "latest_open_time": latest_open_time,
                    "age_minutes": age_minutes,
                    "threshold_minutes": threshold_minutes,
                    "is_stale": is_stale,
                    "generated_at": metadata.get("generated_at") if metadata else None,
                }
                
                # Get last ingestion time
                status["last_ingestion_times"][interval] = self._last_ingestion_times.get(interval)
                
                # Count stale intervals
                if is_stale:
                    status["stale_counts"][interval] = status["stale_counts"].get(interval, 0) + 1
                    
            except Exception as exc:
                logger.warning(f"Error checking freshness for {interval}: {exc}")
                status["intervals"][interval] = {
                    "status": "error",
                    "error": str(exc),
                }
        
        return status
    
    def record_no_trades(self, root_cause: str | None = None) -> None:
        """Record a NO_TRADES event for observability."""
        key = root_cause or "unknown"
        self._no_trades_counts[key] = self._no_trades_counts.get(key, 0) + 1
        logger.debug(f"NO_TRADES recorded: {key} (total: {self._no_trades_counts[key]})")
    
    def record_ingestion(self, interval: str, timestamp: str | None = None) -> None:
        """Record when ingestion was last run for an interval."""
        self._last_ingestion_times[interval] = timestamp or datetime.now(timezone.utc).isoformat()
        logger.debug(f"Ingestion recorded for {interval}: {self._last_ingestion_times[interval]}")
    
    def should_emit_stale_warning(self, interval: str, window_key: str, cooldown_seconds: int = 3600) -> bool:
        """
        Check if stale warning should be emitted (deduplication).
        
        Args:
            interval: Data interval (e.g., "1h", "1d")
            window_key: Unique key for the window/context (e.g., "performance_summary")
            cooldown_seconds: Cooldown period in seconds (default: 1 hour)
            
        Returns:
            True if warning should be emitted, False if it should be suppressed
        """
        key = f"{interval}:{window_key}"
        now = datetime.now(timezone.utc).timestamp()
        last_emitted = self._stale_warnings_emitted[interval].get(window_key, 0)
        
        if now - last_emitted >= cooldown_seconds:
            self._stale_warnings_emitted[interval][window_key] = now
            return True
        
        return False
    
    def get_aggregated_counts(self) -> dict[str, Any]:
        """Get aggregated counts for observability dashboard."""
        return {
            "no_trades_by_cause": dict(self._no_trades_counts),
            "total_no_trades": sum(self._no_trades_counts.values()),
            "stale_warnings_emitted": {
                interval: len(windows) 
                for interval, windows in self._stale_warnings_emitted.items()
            },
        }


# Global instance
_freshness_tracker = FreshnessTrackingService()


def get_freshness_tracker() -> FreshnessTrackingService:
    """Get global freshness tracking service instance."""
    return _freshness_tracker

