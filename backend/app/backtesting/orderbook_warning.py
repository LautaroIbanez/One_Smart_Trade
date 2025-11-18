"""Order book warning exception for tracking fallback scenarios."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OrderBookWarning:
    """Warning raised when order book is unavailable and fallback mode is used."""
    
    symbol: str
    timestamp: str
    reason: str  # "not_found", "out_of_tolerance", "file_not_found", etc.
    tolerance_seconds: int | None = None
    
    def __str__(self) -> str:
        """String representation of warning."""
        msg = f"OrderBookWarning: {self.symbol} at {self.timestamp} - {self.reason}"
        if self.tolerance_seconds:
            msg += f" (tolerance: {self.tolerance_seconds}s)"
        return msg
    
    def to_dict(self) -> dict[str, str | int]:
        """Convert warning to dictionary."""
        result: dict[str, str | int] = {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "reason": self.reason,
        }
        if self.tolerance_seconds:
            result["tolerance_seconds"] = self.tolerance_seconds
        return result

