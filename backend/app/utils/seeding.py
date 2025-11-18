"""Utilities for deterministic random seeding based on date and symbol."""
from __future__ import annotations

import hashlib
from datetime import datetime


def generate_deterministic_seed(date: str | datetime, symbol: str = "BTCUSDT") -> int:
    """
    Generate a deterministic seed from date and symbol.
    
    The seed is derived from YYYYMMDD + symbol to ensure that:
    - Same date + same symbol = same seed
    - Different dates or symbols = different seeds
    - Seed is reproducible across multiple executions
    
    Args:
        date: Date string (YYYY-MM-DD) or datetime object
        symbol: Trading symbol (default: "BTCUSDT")
    
    Returns:
        Integer seed value (0 to 2^31-1)
    
    Example:
        >>> seed1 = generate_deterministic_seed("2025-01-15", "BTCUSDT")
        >>> seed2 = generate_deterministic_seed("2025-01-15", "BTCUSDT")
        >>> assert seed1 == seed2  # Same date + symbol = same seed
        
        >>> seed3 = generate_deterministic_seed("2025-01-16", "BTCUSDT")
        >>> assert seed1 != seed3  # Different date = different seed
    """
    # Normalize date to YYYYMMDD format
    if isinstance(date, datetime):
        date_str = date.strftime("%Y%m%d")
    elif isinstance(date, str):
        # Try to parse and normalize
        try:
            dt = datetime.strptime(date[:10], "%Y-%m-%d")
            date_str = dt.strftime("%Y%m%d")
        except (ValueError, TypeError):
            # Fallback: try to extract YYYYMMDD directly
            date_str = date.replace("-", "").replace("/", "")[:8]
            if len(date_str) != 8:
                raise ValueError(f"Invalid date format: {date}. Expected YYYY-MM-DD or YYYYMMDD")
    else:
        raise TypeError(f"date must be str or datetime, got {type(date)}")
    
    # Normalize symbol to uppercase
    symbol_upper = symbol.upper().strip()
    
    # Create deterministic string: YYYYMMDD + symbol
    seed_string = f"{date_str}{symbol_upper}"
    
    # Generate hash and convert to integer seed
    # Use SHA-256 and take first 8 hex digits (32 bits) to ensure reproducibility
    hash_obj = hashlib.sha256(seed_string.encode("utf-8"))
    hash_hex = hash_obj.hexdigest()[:8]  # First 8 hex digits = 32 bits
    
    # Convert to integer (0 to 2^32-1), then modulo to fit in int32 range
    seed = int(hash_hex, 16) % (2**31 - 1)
    
    return seed

