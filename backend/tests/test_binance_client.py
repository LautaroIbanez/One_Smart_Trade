"""Tests for Binance client."""
import pytest
from unittest.mock import AsyncMock, Mock, patch
from app.data.binance_client import BinanceClient


@pytest.mark.asyncio
async def test_ping():
    """Test ping endpoint - BinanceClient doesn't have ping method, skip this test."""
    # BinanceClient doesn't implement ping, only get_klines
    pass


@pytest.mark.asyncio
async def test_get_klines():
    """Test get klines returns tuple of (data, meta) and records metrics with labels."""
    client = BinanceClient()
    mock_klines = [
        [1609459200000, "29000", "29500", "28800", "29300", "100.5", 1609462799999, "2930000", 100, "50.5", "1475000", "0"],
    ]
    with patch("app.data.binance_client.httpx.AsyncClient") as mock_client_class:
        mock_response = Mock()
        mock_response.json.return_value = mock_klines
        mock_response.raise_for_status = Mock()
        # Mock elapsed for latency calculation
        mock_response.elapsed.total_seconds.return_value = 0.5
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)
        with patch("app.data.binance_client._rate_limiter.acquire", new_callable=AsyncMock):
            # This should not raise ValueError about missing labels
            try:
                data, meta = await client.get_klines("BTCUSDT", "1h", limit=1)
            except ValueError as e:
                if "missing label values" in str(e) or "histogram metric is missing label" in str(e):
                    pytest.fail(f"get_klines raised ValueError about missing labels: {e}")
                raise
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0][0] == 1609459200000
        assert "symbol" in meta
        assert meta["symbol"] == "BTCUSDT"

