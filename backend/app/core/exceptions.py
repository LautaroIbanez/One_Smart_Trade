"""Custom exceptions for the application."""
from __future__ import annotations

from typing import Any


class RiskValidationError(Exception):
    """Exception raised when risk validation fails before generating signals."""
    
    def __init__(self, reason: str, audit_type: str = "capital_missing", context_data: dict[str, Any] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.audit_type = audit_type
        self.context_data = context_data or {}


class DataFreshnessError(Exception):
    """Exception raised when OHLCV data is stale or missing."""
    
    def __init__(self, reason: str, interval: str, latest_timestamp: Any | None = None, threshold_minutes: int | None = None, context_data: dict[str, Any] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.interval = interval
        self.latest_timestamp = latest_timestamp
        self.threshold_minutes = threshold_minutes
        self.context_data = context_data or {}


class DataGapError(Exception):
    """Exception raised when data gaps exceed tolerance threshold."""
    
    def __init__(self, reason: str, interval: str, gaps: list[dict[str, Any]], tolerance_candles: int | None = None, context_data: dict[str, Any] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.interval = interval
        self.gaps = gaps
        self.tolerance_candles = tolerance_candles
        self.context_data = context_data or {}


class RecommendationGenerationError(Exception):
    """Exception raised when recommendation generation fails (audit failed, invalid, etc.)."""
    
    def __init__(self, status: str, reason: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(reason)
        self.status = status
        self.reason = reason
        self.details = details or {}