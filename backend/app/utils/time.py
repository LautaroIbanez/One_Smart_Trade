"""Shared timestamp utilities for consistent serialization and parsing."""
from datetime import datetime, timezone
from typing import Any

import pandas as pd


def serialize_timestamp_utc(ts: pd.Timestamp | datetime | str | None) -> str | None:
    """
    Serialize timestamp to timezone-aware ISO format (UTC).
    
    Ensures timestamps are always serialized with explicit UTC timezone suffix
    for consistent parsing across the codebase.
    
    Args:
        ts: Timestamp to serialize (can be pd.Timestamp, datetime, or ISO string)
        
    Returns:
        ISO format string with UTC timezone suffix (e.g., "2024-01-01T12:00:00+00:00")
        or None if input is None
    """
    if ts is None:
        return None
    
    # Convert to pd.Timestamp if needed
    if isinstance(ts, str):
        # Try parsing first
        parsed = pd.to_datetime(ts, utc=True)
        ts = parsed
    elif isinstance(ts, datetime):
        # Convert datetime to pd.Timestamp
        if ts.tzinfo is None:
            ts = pd.Timestamp(ts).tz_localize("UTC")
        else:
            ts = pd.Timestamp(ts).tz_convert("UTC")
    elif isinstance(ts, pd.Timestamp):
        # Ensure UTC timezone
        if ts.tz is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
    
    # Serialize with explicit UTC timezone
    # pd.Timestamp.isoformat() includes timezone for tz-aware timestamps
    iso_str = ts.isoformat()
    # Ensure it has timezone suffix - pandas uses +00:00 for UTC
    # Check if it ends with timezone indicator
    has_tz_suffix = (
        iso_str.endswith(("+00:00", "Z", "-00:00")) or
        (len(iso_str) > 6 and iso_str[-6] == "+" and ":" in iso_str[-5:])
    )
    if not has_tz_suffix:
        iso_str = iso_str + "+00:00"
    
    return iso_str


def parse_timestamp_utc(value: Any) -> pd.Timestamp | None:
    """
    Parse timestamp to timezone-aware UTC pd.Timestamp.
    
    Handles both naive and timezone-aware ISO strings, ensuring consistent
    UTC timezone-aware output for downstream processing.
    
    Args:
        value: Timestamp value to parse (string, datetime, pd.Timestamp, or numeric)
        
    Returns:
        Timezone-aware UTC pd.Timestamp, or None if parsing fails
    """
    if value is None or pd.isna(value):
        return None
    
    try:
        # Handle numeric epoch values
        if pd.api.types.is_numeric_dtype(type(value)) or isinstance(value, (int, float)):
            if value > 1e12:
                # Likely milliseconds
                return pd.to_datetime(value, unit="ms", utc=True)
            else:
                # Likely seconds
                return pd.to_datetime(value, unit="s", utc=True)
        
        # Parse string or datetime-like
        result = pd.to_datetime(value, utc=True)
        
        # Ensure timezone-aware UTC
        if isinstance(result, pd.Timestamp):
            if result.tz is None:
                # Naive timestamp - localize to UTC
                result = result.tz_localize("UTC")
            else:
                # Timezone-aware - convert to UTC
                result = result.tz_convert("UTC")
        
        return result
    except (ValueError, TypeError, OverflowError):
        return None

