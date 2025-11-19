"""Utilities for deterministic random seeding based on date and symbol."""
from __future__ import annotations

import hashlib
from datetime import date as DateType, datetime


def _normalize_date_string(date_value: str | datetime | DateType) -> str:
    """Return a YYYY-MM-DD string from supported date inputs."""

    if isinstance(date_value, (datetime, DateType)):
        return date_value.strftime("%Y-%m-%d")

    if isinstance(date_value, str):
        normalized = date_value.strip()

        # Try common formats first
        for fmt, length in (("%Y-%m-%d", 10), ("%Y%m%d", 8)):
            try:
                dt = datetime.strptime(normalized[:length], fmt)
                return dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                continue

        # Last-resort fallback: attempt to keep digits only and format
        digits = normalized.replace("-", "").replace("/", "")
        if len(digits) >= 8:
            try:
                dt = datetime.strptime(digits[:8], "%Y%m%d")
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                pass

        raise ValueError(f"Invalid date format: {date_value}. Expected YYYY-MM-DD or YYYYMMDD")

    raise TypeError(f"date_value must be str or datetime, got {type(date_value)}")


def generate_deterministic_seed(date_value: str | datetime | DateType, symbol: str = "BTCUSDT") -> int:
    """Generate a deterministic seed from date and symbol.

    The seed is derived from the YYYY-MM-DD representation of the date plus the
    trading symbol to ensure that:
    - Same date + same symbol = same seed
    - Different dates or symbols = different seeds
    - Seed is reproducible across multiple executions

    Args:
        date_value: Date string (YYYY-MM-DD), datetime object, or date object
        symbol: Trading symbol (default: "BTCUSDT")

    Returns:
        Integer seed value (0 to 2^31-1)
    """

    date_str = _normalize_date_string(date_value)

    # Normalize symbol to uppercase
    symbol_upper = symbol.upper().strip()

    # Create deterministic string: YYYY-MM-DD + symbol
    seed_string = f"{date_str}-{symbol_upper}"

    # Generate hash and convert to integer seed
    # Use SHA-256 and take first 8 hex digits (32 bits) to ensure reproducibility
    hash_obj = hashlib.sha256(seed_string.encode("utf-8"))
    hash_hex = hash_obj.hexdigest()[:8]  # First 8 hex digits = 32 bits

    # Convert to integer (0 to 2^32-1), then modulo to fit in int32 range
    seed = int(hash_hex, 16) % (2**31 - 1)

    return seed
