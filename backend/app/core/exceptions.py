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

