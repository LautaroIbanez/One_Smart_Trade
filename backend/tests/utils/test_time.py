"""Tests for timestamp serialization and parsing utilities."""
import pandas as pd
import pytest
from datetime import datetime, timezone

from app.utils.time import serialize_timestamp_utc, parse_timestamp_utc


def test_serialize_timestamp_utc_with_timezone_aware():
    """serialize_timestamp_utc should preserve UTC timezone in output."""
    ts = pd.Timestamp("2024-01-01T12:00:00", tz="UTC")
    result = serialize_timestamp_utc(ts)
    assert result is not None
    assert "+00:00" in result or result.endswith("Z")
    assert "2024-01-01T12:00:00" in result


def test_serialize_timestamp_utc_with_naive():
    """serialize_timestamp_utc should localize naive timestamps to UTC."""
    ts = pd.Timestamp("2024-01-01T12:00:00")  # Naive
    result = serialize_timestamp_utc(ts)
    assert result is not None
    assert "+00:00" in result or result.endswith("Z")


def test_serialize_timestamp_utc_with_datetime():
    """serialize_timestamp_utc should handle datetime objects."""
    dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    result = serialize_timestamp_utc(dt)
    assert result is not None
    assert "+00:00" in result or result.endswith("Z")


def test_serialize_timestamp_utc_with_string():
    """serialize_timestamp_utc should parse and serialize ISO strings."""
    iso_str = "2024-01-01T12:00:00+00:00"
    result = serialize_timestamp_utc(iso_str)
    assert result is not None
    assert "+00:00" in result or result.endswith("Z")


def test_serialize_timestamp_utc_with_none():
    """serialize_timestamp_utc should return None for None input."""
    assert serialize_timestamp_utc(None) is None


def test_parse_timestamp_utc_with_timezone_aware_string():
    """parse_timestamp_utc should parse timezone-aware ISO strings."""
    iso_str = "2024-01-01T12:00:00+00:00"
    result = parse_timestamp_utc(iso_str)
    assert result is not None
    assert isinstance(result, pd.Timestamp)
    assert result.tz is not None
    assert result.tz.zone == "UTC" or str(result.tz) == "UTC"


def test_parse_timestamp_utc_with_naive_string():
    """parse_timestamp_utc should localize naive ISO strings to UTC."""
    iso_str = "2024-01-01T12:00:00"  # Naive
    result = parse_timestamp_utc(iso_str)
    assert result is not None
    assert isinstance(result, pd.Timestamp)
    assert result.tz is not None
    assert result.tz.zone == "UTC" or str(result.tz) == "UTC"


def test_parse_timestamp_utc_with_epoch_milliseconds():
    """parse_timestamp_utc should handle epoch milliseconds."""
    epoch_ms = 1704110400000  # 2024-01-01T12:00:00Z
    result = parse_timestamp_utc(epoch_ms)
    assert result is not None
    assert isinstance(result, pd.Timestamp)
    assert result.tz is not None


def test_parse_timestamp_utc_with_epoch_seconds():
    """parse_timestamp_utc should handle epoch seconds."""
    epoch_s = 1704110400  # 2024-01-01T12:00:00Z
    result = parse_timestamp_utc(epoch_s)
    assert result is not None
    assert isinstance(result, pd.Timestamp)
    assert result.tz is not None


def test_parse_timestamp_utc_with_invalid_string():
    """parse_timestamp_utc should return None for invalid strings."""
    invalid = "not-a-timestamp"
    result = parse_timestamp_utc(invalid)
    assert result is None


def test_parse_timestamp_utc_with_none():
    """parse_timestamp_utc should return None for None input."""
    assert parse_timestamp_utc(None) is None


def test_roundtrip_serialization_naive():
    """Roundtrip: naive timestamp -> serialize -> parse should preserve time."""
    original = pd.Timestamp("2024-01-01T12:00:00")  # Naive
    serialized = serialize_timestamp_utc(original)
    parsed = parse_timestamp_utc(serialized)
    
    assert parsed is not None
    # Time should be preserved (localized to UTC)
    assert parsed.hour == original.hour
    assert parsed.minute == original.minute
    assert parsed.second == original.second
    # Should be timezone-aware UTC
    assert parsed.tz is not None
    assert parsed.tz.zone == "UTC" or str(parsed.tz) == "UTC"


def test_roundtrip_serialization_timezone_aware():
    """Roundtrip: tz-aware timestamp -> serialize -> parse should preserve time."""
    original = pd.Timestamp("2024-01-01T12:00:00", tz="UTC")
    serialized = serialize_timestamp_utc(original)
    parsed = parse_timestamp_utc(serialized)
    
    assert parsed is not None
    # Time should be preserved
    assert parsed.hour == original.hour
    assert parsed.minute == original.minute
    assert parsed.second == original.second
    # Should be timezone-aware UTC
    assert parsed.tz is not None
    assert parsed.tz.zone == "UTC" or str(parsed.tz) == "UTC"


def test_roundtrip_serialization_mixed_formats():
    """Roundtrip should work with various input formats."""
    test_cases = [
        "2024-01-01T12:00:00+00:00",
        "2024-01-01T12:00:00Z",
        "2024-01-01T12:00:00",  # Naive
        pd.Timestamp("2024-01-01T12:00:00", tz="UTC"),
        pd.Timestamp("2024-01-01T12:00:00"),  # Naive
        datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    ]
    
    for test_input in test_cases:
        serialized = serialize_timestamp_utc(test_input)
        assert serialized is not None, f"Failed to serialize: {test_input}"
        
        parsed = parse_timestamp_utc(serialized)
        assert parsed is not None, f"Failed to parse: {serialized}"
        assert isinstance(parsed, pd.Timestamp)
        assert parsed.tz is not None, f"Parsed timestamp not timezone-aware: {parsed}"


def test_parse_timestamp_utc_preserves_no_nat_rows():
    """parse_timestamp_utc should not create NaT for valid timestamps."""
    valid_timestamps = [
        "2024-01-01T12:00:00+00:00",
        "2024-01-01T12:00:00Z",
        "2024-01-01T12:00:00",
        pd.Timestamp("2024-01-01T12:00:00", tz="UTC"),
    ]
    
    for ts_input in valid_timestamps:
        result = parse_timestamp_utc(ts_input)
        assert result is not None, f"Valid timestamp became None: {ts_input}"
        assert not pd.isna(result), f"Valid timestamp became NaT: {ts_input}"
        assert isinstance(result, pd.Timestamp)
        assert result.tz is not None


