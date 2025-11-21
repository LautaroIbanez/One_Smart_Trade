#!/usr/bin/env python3
"""
Script rápido para verificar que el preflight es resiliente a fallos de métricas.

Este script simula fallos de métricas y verifica que el preflight continúe.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.preflight import run_preflight
from app.data.binance_client import BinanceClient
from app.observability.metrics import BINANCE_REQUEST_LATENCY, record_data_gap


async def test_preflight_with_metric_failures():
    """Test que el preflight continúa aunque las métricas fallen."""
    print("Testing preflight resilience to metric failures...")
    print("-" * 60)
    
    # Test 1: record_data_gap failure
    print("\nTest 1: record_data_gap failure")
    print("  Simulating ValueError in record_data_gap...")
    
    with patch("app.services.preflight.record_data_gap") as mock_record:
        mock_record.side_effect = ValueError("histogram metric is missing label values")
        
        mock_ingestion = MagicMock()
        mock_ingestion.check_gaps.return_value = [
            {
                "status": "gap",
                "interval": "1h",
                "start": (datetime.utcnow() - timedelta(days=1)).isoformat(),
                "end": datetime.utcnow().isoformat(),
                "missing_candles": 10,
            }
        ]
        mock_ingestion.ingest_timeframe = AsyncMock(return_value={
            "status": "success",
            "interval": "1h",
            "rows": 100,
        })
        
        mock_curation = MagicMock()
        mock_curation.curate_interval.return_value = {"status": "success"}
        
        with patch("app.services.preflight.DataIngestion", return_value=mock_ingestion):
            with patch("app.services.preflight.DataCuration", return_value=mock_curation):
                with patch("app.services.preflight.SessionLocal"):
                    with patch("app.services.preflight.log_run"):
                        try:
                            await run_preflight(days=1, intervals=("1h",))
                            print("  ✓ Preflight completed despite record_data_gap failure")
                        except ValueError as e:
                            if "missing label" in str(e).lower():
                                print(f"  ❌ FAILED: Preflight raised ValueError: {e}")
                                return 1
                            raise
    
    # Test 2: BINANCE_REQUEST_LATENCY failure
    print("\nTest 2: BINANCE_REQUEST_LATENCY failure")
    print("  Simulating ValueError in BINANCE_REQUEST_LATENCY.observe()...")
    
    client = BinanceClient()
    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_response.elapsed.total_seconds.return_value = 0.5
    mock_response.raise_for_status = MagicMock()
    
    with patch("app.data.binance_client.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client
        
        with patch("app.data.binance_client._rate_limiter.acquire", new_callable=AsyncMock):
            # Mock BINANCE_REQUEST_LATENCY to raise ValueError (patch where it's imported)
            with patch("app.observability.metrics.BINANCE_REQUEST_LATENCY") as mock_metric:
                mock_labeled = MagicMock()
                mock_labeled.observe.side_effect = ValueError("histogram metric is missing label values")
                mock_metric.labels.return_value = mock_labeled
                
                try:
                    await client.get_klines("BTCUSDT", "1h")
                    print("  ✓ get_klines completed despite metric failure")
                except ValueError as e:
                    if "missing label" in str(e).lower():
                        print(f"  ❌ FAILED: get_klines raised ValueError: {e}")
                        return 1
                    raise
    
    print("\n" + "=" * 60)
    print("✅ All resilience tests passed!")
    print("=" * 60)
    return 0


async def main():
    """Run all tests."""
    try:
        return await test_preflight_with_metric_failures()
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

