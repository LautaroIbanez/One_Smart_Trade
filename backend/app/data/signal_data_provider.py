"""Single source-of-truth for signal generation data inputs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from app.core.config import settings
from app.core.logging import logger
from app.data.curation import DataCuration
from app.core.exceptions import DataFreshnessError, DataGapError


@dataclass(frozen=True, slots=True)
class SignalDataInputs:
    """Immutable container for validated signal generation inputs."""
    
    df_1h: pd.DataFrame
    df_1d: pd.DataFrame
    venue: str
    symbol: str
    metadata: dict[str, Any] | None = None  # Optional metadata about data freshness, staleness, etc.
    
    def __post_init__(self) -> None:
        """Validate inputs after initialization."""
        if self.df_1h.empty:
            raise ValueError("1h dataframe cannot be empty")
        if self.df_1d.empty:
            raise ValueError("1d dataframe cannot be empty")
        if "open_time" not in self.df_1h.columns:
            raise ValueError("1h dataframe must have 'open_time' column")
        if "open_time" not in self.df_1d.columns:
            raise ValueError("1d dataframe must have 'open_time' column")


class SignalDataProvider:
    """
    Single source-of-truth for signal generation data inputs.
    
    This class ensures that all strategies receive the same validated datasets,
    avoiding direct filesystem reads and ensuring consistency across the signal
    generation pipeline.
    """
    
    def __init__(
        self,
        curation: DataCuration | None = None,
        *,
        venue: str = "binance",
        symbol: str = "BTCUSDT",
    ) -> None:
        """
        Initialize signal data provider.
        
        Args:
            curation: Optional DataCuration instance (creates new one if not provided)
            venue: Trading venue (default: "binance")
            symbol: Trading symbol (default: "BTCUSDT")
        """
        self.curation = curation or DataCuration()
        self.venue = venue
        self.symbol = symbol
        self._cached_inputs: SignalDataInputs | None = None
        self._last_metadata: dict[str, Any] | None = None  # Cache last metadata for inspection
    
    def get_validated_inputs(
        self,
        *,
        force_refresh: bool = False,
        validate_freshness: bool = True,
        validate_gaps: bool = True,
    ) -> SignalDataInputs:
        """
        Get validated data inputs for signal generation.
        
        This method ensures:
        - Data freshness validation (if enabled)
        - Data gap validation (if enabled)
        - Consistent datasets across all strategies
        - Immutable data container to prevent modifications
        
        Args:
            force_refresh: Force refresh from filesystem (ignore cache)
            validate_freshness: Validate data freshness before returning
            validate_gaps: Validate data gaps before returning
            
        Returns:
            SignalDataInputs: Immutable container with validated 1h and 1d dataframes
            
        Raises:
            DataFreshnessError: If data freshness validation fails
            DataGapError: If data gap validation fails
            FileNotFoundError: If curated data files are not found
            ValueError: If dataframes are empty or invalid
        """
        # Check if cache should be invalidated based on latest_open_time
        # Tighten freshness checks even in dev: warn + force cache invalidation when stale
        should_invalidate_cache = False
        if self._cached_inputs is not None and not force_refresh:
            # Check if latest_open_time is stale (for 1d interval, check if < today-2d)
            try:
                metadata_1d = self.curation.get_curated_metadata("1d", venue=self.venue, symbol=self.symbol)
                if metadata_1d and "latest_open_time" in metadata_1d:
                    latest_open_time_str = metadata_1d["latest_open_time"]
                    latest_dt = self._normalize_open_time(latest_open_time_str)
                    if latest_dt:
                        now = datetime.now(timezone.utc)
                        days_old = (now - latest_dt).days
                        # If 1d data is older than 2 days, invalidate cache and trigger ingestion
                        # This check applies even in dev mode (tightened requirement)
                        if days_old >= 2:
                            should_invalidate_cache = True
                            dev_mode = settings.is_dev_mode()
                            logger.warning(
                                "Cache invalidated: latest_open_time is stale (even in dev mode)",
                                extra={
                                    "interval": "1d",
                                    "latest_open_time": latest_open_time_str,
                                    "days_old": days_old,
                                    "threshold_days": 2,
                                    "dev_mode": dev_mode,
                                    "cache_invalidated": True,
                                },
                            )
                            # Log that ingestion should be triggered (actual triggering should be done by scheduled job or API)
                            logger.info(
                                "Data is stale - ingestion should be triggered",
                                extra={
                                    "interval": "1d",
                                    "latest_open_time": latest_open_time_str,
                                    "days_old": days_old,
                                    "should_trigger_ingestion": True,
                                    "dev_mode": dev_mode,
                                },
                            )
            except Exception as exc:
                logger.debug(f"Could not check cache invalidation: {exc}")
        
        # Return cached inputs if available and not forcing refresh and cache is still valid
        if self._cached_inputs is not None and not force_refresh and not should_invalidate_cache:
            logger.debug("Returning cached signal data inputs")
            return self._cached_inputs
        
        # Clear cache if invalidated
        if should_invalidate_cache:
            self._cached_inputs = None
        
        logger.info("Loading validated signal data inputs", extra={"venue": self.venue, "symbol": self.symbol})
        
        # Check if dev mode is enabled (unified check) - do this early for use in freshness checks
        dev_mode = settings.is_dev_mode()
        
        # Initialize metadata tracking
        metadata: dict[str, Any] = {
            "status": "ok",
            "dev_mode": dev_mode,
            "used_legacy_fallback": False,
            "intervals": {},
        }
        
        # Validate data freshness if requested
        # Tighten freshness checks even in dev: warn + force cache invalidation when stale
        if validate_freshness:
            try:
                # 1d uses interval-specific threshold (48 hours by default), allowing yesterday's candle
                # In dev mode, validation is skipped but freshness is still logged and cache is invalidated if stale
                self.curation.validate_data_freshness("1d", venue=self.venue, symbol=self.symbol, skip_in_dev=True)
                # 1h uses default threshold (90 minutes)
                # In dev mode, validation is skipped but freshness is still logged and cache is invalidated if stale
                self.curation.validate_data_freshness("1h", venue=self.venue, symbol=self.symbol, skip_in_dev=True)
                logger.debug("Data freshness validation passed")
            except DataFreshnessError as exc:
                # Even in dev mode, invalidate cache when data is stale (tightened requirement)
                should_invalidate_cache = True
                if self._cached_inputs is not None:
                    self._cached_inputs = None
                    logger.warning(
                        "Cache invalidated due to stale data (even in dev mode)",
                        extra={
                            "interval": exc.interval,
                            "latest_timestamp": exc.latest_timestamp,
                            "threshold_minutes": exc.threshold_minutes,
                            "dev_mode": dev_mode,
                            "cache_invalidated": True,
                        },
                    )
                
                if dev_mode:
                    # In dev mode, log the failure but don't raise - allow stale data to proceed
                    # Extract freshness metadata
                    latest_timestamp = exc.latest_timestamp
                    threshold_minutes = exc.threshold_minutes
                    context_data = getattr(exc, "context_data", {}) or {}
                    age_minutes = context_data.get("age_minutes")
                    
                    # Calculate stale_minutes if not provided
                    if age_minutes is None and latest_timestamp:
                        try:
                            latest_dt = pd.to_datetime(latest_timestamp)
                            if latest_dt.tz is None:
                                latest_dt = latest_dt.tz_localize(timezone.utc)
                            else:
                                latest_dt = latest_dt.tz_convert(timezone.utc)
                            now = datetime.now(timezone.utc)
                            age_minutes = (now - latest_dt.to_pydatetime()).total_seconds() / 60.0
                        except Exception:
                            age_minutes = None
                    
                    # Store metadata for this interval
                    metadata["intervals"][exc.interval] = {
                        "latest_timestamp": latest_timestamp,
                        "stale_minutes": age_minutes,
                        "threshold_minutes": threshold_minutes,
                        "status": "stale",
                    }
                    
                    self._record_data_freshness_failure(exc)
                    logger.warning(
                        "DEV MODE: Data freshness validation failed - cache invalidated, continuing with stale data",
                        extra={
                            "interval": exc.interval,
                            "latest_timestamp": latest_timestamp,
                            "stale_minutes": age_minutes,
                            "threshold_minutes": threshold_minutes,
                            "dev_mode": True,
                            "cache_invalidated": True,
                        },
                    )
                else:
                    self._record_data_freshness_failure(exc)
                    raise
        
        # Validate data gaps if requested
        # In dev mode, validation will be skipped by curation.validate_data_gaps() but status is still logged
        if validate_gaps:
            try:
                # 1d uses interval-specific tolerance (15 candles by default), more lenient for historical data
                # In dev mode, validation is skipped but gap status is still logged
                self.curation.validate_data_gaps("1d", venue=self.venue, symbol=self.symbol, skip_in_dev=True)
                # 1h uses default tolerance (2 candles)
                # In dev mode, validation is skipped but gap status is still logged
                self.curation.validate_data_gaps("1h", venue=self.venue, symbol=self.symbol, skip_in_dev=True)
                logger.debug("Data gap validation passed")
            except DataGapError as exc:
                if dev_mode:
                    # In dev mode, log the failure but don't raise - allow gapped data to proceed
                    logger.info(
                        "DEV MODE: Data gap validation failed but continuing with gapped data",
                        extra={
                            "interval": exc.interval,
                            "gaps": exc.gaps,
                            "tolerance_candles": exc.tolerance_candles,
                            "dev_mode": True,
                        },
                    )
                else:
                    raise
        
        # Load curated datasets with verification and fallback
        used_legacy_fallback_1d = False
        used_legacy_fallback_1h = False
        
        try:
            df_1d = self.curation.get_latest_curated("1d", venue=self.venue, symbol=self.symbol)
        except FileNotFoundError:
            # Check if raw data exists to determine if reingestion is needed
            from app.data.storage import get_raw_path, RAW_ROOT
            raw_1d_path = get_raw_path(self.venue, self.symbol, "1d").parent
            raw_files_exist = raw_1d_path.exists() and any(raw_1d_path.glob("*.parquet"))
            
            if dev_mode:
                if not raw_files_exist:
                    logger.warning(
                        "DEV MODE: 1d data missing (no raw files found). Pipeline should trigger reingestion on startup.",
                        extra={
                            "venue": self.venue,
                            "symbol": self.symbol,
                            "raw_path": str(raw_1d_path),
                            "dev_mode": True,
                        },
                    )
                else:
                    logger.info(
                        "DEV MODE: 1d curated data missing but raw data exists. Curation may be needed.",
                        extra={"venue": self.venue, "symbol": self.symbol, "dev_mode": True},
                    )
            
            # Fallback to legacy path structure
            logger.warning("Partitioned 1d data not found, falling back to legacy path")
            used_legacy_fallback_1d = True
            try:
                df_1d = self.curation.get_latest_curated("1d")
            except FileNotFoundError:
                if dev_mode:
                    # In dev mode, allow empty dataframe to proceed with warning
                    logger.warning(
                        "DEV MODE: No 1d data available (neither partitioned nor legacy). Signal generation may fail or use degraded mode.",
                        extra={"venue": self.venue, "symbol": self.symbol, "dev_mode": True},
                    )
                    # Create empty dataframe as fallback - will be caught by validation below
                    df_1d = pd.DataFrame()
                else:
                    raise
        
        try:
            df_1h = self.curation.get_latest_curated("1h", venue=self.venue, symbol=self.symbol)
        except FileNotFoundError:
            # Fallback to legacy path structure
            logger.warning("Partitioned 1h data not found, falling back to legacy path")
            used_legacy_fallback_1h = True
            df_1h = self.curation.get_latest_curated("1h")
        
        # Track if legacy fallback was used
        metadata["used_legacy_fallback"] = used_legacy_fallback_1d or used_legacy_fallback_1h
        
        # Validate dataframes are not empty
        if df_1d is None or df_1d.empty:
            metadata["status"] = "stale_or_missing"
            raise ValueError("1d curated dataset is empty")
        
        if df_1h is None or df_1h.empty:
            logger.warning("1h dataset empty, using 1d as fallback")
            df_1h = df_1d.copy()
            metadata["status"] = "stale_or_missing"
        
        # Mark as stale_or_missing if legacy fallback was used
        if metadata["used_legacy_fallback"]:
            metadata["status"] = "stale_or_missing"
        
        # Calculate latest timestamps and stale_minutes for metadata if not already set
        if "1d" not in metadata.get("intervals", {}):
            try:
                if "open_time" in df_1d.columns:
                    latest_1d = df_1d["open_time"].max()
                    latest_1d_dt = self._normalize_open_time(latest_1d)
                    if latest_1d_dt:
                        now = datetime.now(timezone.utc)
                        stale_minutes_1d = (now - latest_1d_dt).total_seconds() / 60.0
                        if "intervals" not in metadata:
                            metadata["intervals"] = {}
                        metadata["intervals"]["1d"] = {
                            "latest_timestamp": latest_1d_dt.isoformat(),
                            "stale_minutes": round(stale_minutes_1d, 2),
                            "status": "ok" if metadata["status"] == "ok" else metadata["status"],
                        }
            except Exception:
                pass
        
        if "1h" not in metadata.get("intervals", {}):
            try:
                if "open_time" in df_1h.columns:
                    latest_1h = df_1h["open_time"].max()
                    latest_1h_dt = self._normalize_open_time(latest_1h)
                    if latest_1h_dt:
                        now = datetime.now(timezone.utc)
                        stale_minutes_1h = (now - latest_1h_dt).total_seconds() / 60.0
                        if "intervals" not in metadata:
                            metadata["intervals"] = {}
                        metadata["intervals"]["1h"] = {
                            "latest_timestamp": latest_1h_dt.isoformat(),
                            "stale_minutes": round(stale_minutes_1h, 2),
                            "status": "ok" if metadata["status"] == "ok" else metadata["status"],
                        }
            except Exception:
                pass
        
        # Store metadata for external access
        self._last_metadata = metadata
        
        # Create immutable inputs container
        inputs = SignalDataInputs(
            df_1h=df_1h.copy(),  # Copy to prevent external modifications
            df_1d=df_1d.copy(),  # Copy to prevent external modifications
            venue=self.venue,
            symbol=self.symbol,
            metadata=metadata,
        )
        
        # Cache inputs for subsequent calls
        self._cached_inputs = inputs
        
        logger.info(
            "Signal data inputs loaded successfully",
            extra={
                "venue": self.venue,
                "symbol": self.symbol,
                "1h_rows": len(df_1h),
                "1d_rows": len(df_1d),
            },
        )
        
        return inputs
    
    def clear_cache(self) -> None:
        """Clear cached inputs to force refresh on next call."""
        self._cached_inputs = None
        logger.debug("Signal data inputs cache cleared")

    def has_cached_inputs(self) -> bool:
        """Return True if validated inputs are cached in memory."""
        return self._cached_inputs is not None
    
    def get_last_metadata(self) -> dict[str, Any] | None:
        """Return last metadata from get_validated_inputs call."""
        return self._last_metadata

    def describe_dataset_freshness(self, intervals: list[str] | None = None) -> dict[str, Any]:
        """Return latest timestamps and freshness metadata for curated datasets."""
        intervals = intervals or ["1h", "1d"]
        snapshot: dict[str, Any] = {}
        for interval in intervals:
            snapshot[interval] = self._build_interval_freshness(interval)
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "venue": self.venue,
            "symbol": self.symbol,
            "intervals": snapshot,
        }

    def _build_interval_freshness(self, interval: str) -> dict[str, Any]:
        """Inspect curated dataset for interval and compute freshness metrics."""
        try:
            # Try to get latest_open_time from metadata first
            metadata = self.curation.get_curated_metadata(interval, venue=self.venue, symbol=self.symbol)
            latest_open_time_from_meta = None
            if metadata and "latest_open_time" in metadata:
                latest_open_time_from_meta = metadata["latest_open_time"]
            
            df = self.curation.get_latest_curated(interval, venue=self.venue, symbol=self.symbol)
        except FileNotFoundError:
            return {"status": "missing", "latest_open_time": None, "age_minutes": None, "rows": 0}
        if df is None or df.empty:
            return {"status": "empty", "latest_open_time": None, "age_minutes": None, "rows": 0}
        if "open_time" not in df.columns:
            return {"status": "invalid", "latest_open_time": None, "age_minutes": None, "rows": len(df)}
        
        # Use metadata latest_open_time if available, otherwise compute from dataframe
        if latest_open_time_from_meta:
            try:
                latest_dt = self._normalize_open_time(latest_open_time_from_meta)
            except Exception:
                latest_dt = None
        else:
            latest_value = df["open_time"].max()
            latest_dt = self._normalize_open_time(latest_value)
        
        if latest_dt is None:
            return {"status": "unknown", "latest_open_time": None, "age_minutes": None, "rows": len(df)}
        age_minutes = (datetime.now(timezone.utc) - latest_dt).total_seconds() / 60.0
        return {
            "status": "ok",
            "latest_open_time": latest_dt.isoformat(),
            "age_minutes": round(age_minutes, 2),
            "rows": len(df),
        }

    @staticmethod
    def _normalize_open_time(value: Any) -> datetime | None:
        """Convert various open_time representations into timezone-aware datetime."""
        if value is None or pd.isna(value):
            return None
        if isinstance(value, pd.Timestamp):
            ts = value.tz_convert(timezone.utc) if value.tzinfo else value.tz_localize(timezone.utc)
            return ts.to_pydatetime()
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, (int, float)):
            # Heuristic: treat large numbers as milliseconds
            try:
                if value > 1e12:
                    return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)
                return datetime.fromtimestamp(value, tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                return None
        try:
            parsed = pd.to_datetime(value, utc=True)
            if isinstance(parsed, pd.Timestamp):
                return parsed.to_pydatetime()
            return parsed
        except (ValueError, TypeError):
            return None

    def _record_data_freshness_failure(self, exc: DataFreshnessError) -> None:
        """Emit structured telemetry when curated data is stale (with deduplication)."""
        from app.services.freshness_tracking_service import get_freshness_tracker
        
        context = getattr(exc, "context_data", {}) or {}
        age_minutes = context.get("age_minutes")
        
        # Use deduplication: emit warning once per interval per window
        tracker = get_freshness_tracker()
        window_key = f"signal_data_provider_{self.venue}_{self.symbol}"
        should_emit = tracker.should_emit_stale_warning(exc.interval, window_key, cooldown_seconds=3600)
        
        if should_emit:
            logger.warning(
                "Data freshness validation failed",
                extra={
                    "interval": exc.interval,
                    "latest_timestamp": exc.latest_timestamp,
                    "latest_candle_age_minutes": age_minutes,
                    "threshold_minutes": exc.threshold_minutes,
                    "venue": context.get("venue") or self.venue,
                    "symbol": context.get("symbol") or self.symbol,
                    "should_trigger_ingestion": True,
                },
            )
        else:
            logger.debug(
                "Data freshness validation failed (deduplicated)",
                extra={
                    "interval": exc.interval,
                    "latest_timestamp": exc.latest_timestamp,
                    "latest_candle_age_minutes": age_minutes,
                    "threshold_minutes": exc.threshold_minutes,
                },
            )

