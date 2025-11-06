"""Tests for data ingestion."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from app.data.ingestion import DataIngestion


@pytest.mark.asyncio
async def test_ingest_timeframe():
    """Test timeframe ingestion."""
    ingestion = DataIngestion()
    mock_klines = [
        [1609459200000, "29000", "29500", "28800", "29300", "100.5", 1609462799999, "2930000", 100, "50.5", "1475000", "0"],
    ]
    with patch.object(ingestion.client, "get_klines", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_klines
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=1)
        result = await ingestion.ingest_timeframe("1h", start_time, end_time)
        assert result["status"] in ["success", "no_data", "empty"]
        assert result["interval"] == "1h"

