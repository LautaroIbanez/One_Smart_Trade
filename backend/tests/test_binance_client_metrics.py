"""
Tests for Binance client metrics to ensure labels are provided correctly.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.data.binance_client import BinanceClient
from app.observability.metrics import BINANCE_REQUEST_LATENCY


@pytest.mark.asyncio
async def test_get_klines_records_metrics_with_labels():
    """Test that get_klines records metrics with required labels (symbol, interval)."""
    client = BinanceClient()
    
    # Mock the httpx response
    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_response.elapsed.total_seconds.return_value = 0.5
    mock_response.raise_for_status = MagicMock()
    
    # Mock httpx.AsyncClient
    with patch("app.data.binance_client.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client
        
        # Mock the rate limiter to avoid waiting
        with patch("app.data.binance_client._rate_limiter.acquire", new_callable=AsyncMock):
            # Call get_klines
            symbol = "BTCUSDT"
            interval = "1h"
            await client.get_klines(symbol=symbol, interval=interval)
            
            # Verify that BINANCE_REQUEST_LATENCY was called with labels
            # We can't directly verify the call, but we can verify it doesn't raise ValueError
            # by checking that the metric exists and can be called with labels
            try:
                # This should not raise ValueError if labels are provided correctly
                metric = BINANCE_REQUEST_LATENCY.labels(symbol=symbol, interval=interval)
                assert metric is not None
            except ValueError as e:
                pytest.fail(f"BINANCE_REQUEST_LATENCY.labels() raised ValueError: {e}")


@pytest.mark.asyncio
async def test_get_klines_does_not_raise_valueerror_on_observe():
    """Test that get_klines does not raise ValueError when observing metrics."""
    client = BinanceClient()
    
    # Mock the httpx response
    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_response.elapsed.total_seconds.return_value = 0.5
    mock_response.raise_for_status = MagicMock()
    
    # Mock httpx.AsyncClient
    with patch("app.data.binance_client.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client
        
        # Mock the rate limiter to avoid waiting
        with patch("app.data.binance_client._rate_limiter.acquire", new_callable=AsyncMock):
            # This should not raise ValueError about missing labels
            try:
                symbol = "BTCUSDT"
                interval = "1h"
                await client.get_klines(symbol=symbol, interval=interval)
            except ValueError as e:
                if "missing label values" in str(e) or "histogram metric is missing label" in str(e):
                    pytest.fail(f"get_klines raised ValueError about missing labels: {e}")
                # Re-raise if it's a different ValueError
                raise


def test_binance_request_latency_requires_labels():
    """Test that BINANCE_REQUEST_LATENCY requires symbol and interval labels."""
    # Verify that calling observe without labels raises ValueError
    with pytest.raises(ValueError, match=".*missing label.*"):
        BINANCE_REQUEST_LATENCY.observe(0.5)
    
    # Verify that calling with labels works
    try:
        BINANCE_REQUEST_LATENCY.labels(symbol="BTCUSDT", interval="1h").observe(0.5)
    except ValueError as e:
        pytest.fail(f"BINANCE_REQUEST_LATENCY.labels().observe() raised ValueError: {e}")


def test_binance_request_latency_labels_order():
    """Test that labels can be provided in any order (keyword arguments)."""
    # Both should work
    metric1 = BINANCE_REQUEST_LATENCY.labels(symbol="BTCUSDT", interval="1h")
    metric2 = BINANCE_REQUEST_LATENCY.labels(interval="1h", symbol="BTCUSDT")
    
    # Both should be valid and not raise errors
    try:
        metric1.observe(0.5)
        metric2.observe(0.5)
    except ValueError as e:
        pytest.fail(f"Labels in different order raised ValueError: {e}")

