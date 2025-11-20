"""Single source-of-truth for signal generation data inputs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.core.logging import logger
from app.data.curation import DataCuration
from app.core.exceptions import DataFreshnessError


@dataclass(frozen=True, slots=True)
class SignalDataInputs:
    """Immutable container for validated signal generation inputs."""
    
    df_1h: pd.DataFrame
    df_1d: pd.DataFrame
    venue: str
    symbol: str
    
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
        # Return cached inputs if available and not forcing refresh
        if self._cached_inputs is not None and not force_refresh:
            logger.debug("Returning cached signal data inputs")
            return self._cached_inputs
        
        logger.info("Loading validated signal data inputs", extra={"venue": self.venue, "symbol": self.symbol})
        
        # Validate data freshness if requested
        if validate_freshness:
            try:
                self.curation.validate_data_freshness("1d", venue=self.venue, symbol=self.symbol)
                self.curation.validate_data_freshness("1h", venue=self.venue, symbol=self.symbol)
                logger.debug("Data freshness validation passed")
            except DataFreshnessError as exc:
                self._record_data_freshness_failure(exc)
                raise
        
        # Validate data gaps if requested
        if validate_gaps:
            self.curation.validate_data_gaps("1d", venue=self.venue, symbol=self.symbol)
            self.curation.validate_data_gaps("1h", venue=self.venue, symbol=self.symbol)
            logger.debug("Data gap validation passed")
        
        # Load curated datasets
        try:
            df_1d = self.curation.get_latest_curated("1d", venue=self.venue, symbol=self.symbol)
        except FileNotFoundError:
            # Fallback to legacy path structure
            logger.warning("Partitioned 1d data not found, falling back to legacy path")
            df_1d = self.curation.get_latest_curated("1d")
        
        try:
            df_1h = self.curation.get_latest_curated("1h", venue=self.venue, symbol=self.symbol)
        except FileNotFoundError:
            # Fallback to legacy path structure
            logger.warning("Partitioned 1h data not found, falling back to legacy path")
            df_1h = self.curation.get_latest_curated("1h")
        
        # Validate dataframes are not empty
        if df_1d is None or df_1d.empty:
            raise ValueError("1d curated dataset is empty")
        
        if df_1h is None or df_1h.empty:
            logger.warning("1h dataset empty, using 1d as fallback")
            df_1h = df_1d.copy()
        
        # Create immutable inputs container
        inputs = SignalDataInputs(
            df_1h=df_1h.copy(),  # Copy to prevent external modifications
            df_1d=df_1d.copy(),  # Copy to prevent external modifications
            venue=self.venue,
            symbol=self.symbol,
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

    def _record_data_freshness_failure(self, exc: DataFreshnessError) -> None:
        """Emit structured telemetry when curated data is stale."""
        context = getattr(exc, "context_data", {}) or {}
        age_minutes = context.get("age_minutes")
        logger.warning(
            "Data freshness validation failed",
            extra={
                "interval": exc.interval,
                "latest_timestamp": exc.latest_timestamp,
                "latest_candle_age_minutes": age_minutes,
                "threshold_minutes": exc.threshold_minutes,
                "venue": context.get("venue") or self.venue,
                "symbol": context.get("symbol") or self.symbol,
            },
        )

