"""Tests for Binance client."""
import pytest
from unittest.mock import AsyncMock, patch
from app.data.binance_client import BinanceClient


@pytest.mark.asyncio
async def test_ping():
    """Test ping endpoint."""
    client = BinanceClient()
    with patch("app.data.binance_client.httpx.AsyncClient") as mock_client:
        mock_response = AsyncMock()
        mock_response.json.return_value = {}
        mock_response.raise_for_status = AsyncMock()
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
        result = await client.ping()
        assert result == {}


@pytest.mark.asyncio
async def test_get_klines():
    """Test get klines."""
    client = BinanceClient()
    mock_klines = [
        [1609459200000, "29000", "29500", "28800", "29300", "100.5", 1609462799999, "2930000", 100, "50.5", "1475000", "0"],
    ]
    with patch("app.data.binance_client.httpx.AsyncClient") as mock_client:
        mock_response = AsyncMock()
        mock_response.json.return_value = mock_klines
        mock_response.raise_for_status = AsyncMock()
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
        result = await client.get_klines("BTCUSDT", "1h", limit=1)
        assert len(result) == 1
        assert result[0][0] == 1609459200000

