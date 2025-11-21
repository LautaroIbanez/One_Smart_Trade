#!/usr/bin/env python3
"""
Script rápido para verificar que get_klines registra métricas con los labels correctos.

Este script simula una llamada a get_klines y verifica que no se levante ValueError
por labels faltantes.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.data.binance_client import BinanceClient
from app.observability.metrics import BINANCE_REQUEST_LATENCY


async def test_get_klines_metrics():
    """Test que get_klines registra métricas con labels correctos."""
    print("Testing BinanceClient.get_klines metrics recording...")
    
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
            try:
                symbol = "BTCUSDT"
                interval = "1h"
                print(f"  Calling get_klines(symbol='{symbol}', interval='{interval}')...")
                await client.get_klines(symbol=symbol, interval=interval)
                print("  ✓ get_klines completed without errors")
                
                # Verify that we can access the metric with labels
                print(f"  Verifying metric labels (symbol='{symbol}', interval='{interval}')...")
                metric = BINANCE_REQUEST_LATENCY.labels(symbol=symbol, interval=interval)
                print("  ✓ Metric labels are valid")
                
                print("\n✅ Test passed: get_klines records metrics with correct labels")
                return 0
                
            except ValueError as e:
                if "missing label values" in str(e) or "histogram metric is missing label" in str(e):
                    print(f"\n❌ Test failed: ValueError about missing labels: {e}")
                    print("\nThis indicates that BINANCE_REQUEST_LATENCY.observe() was called")
                    print("without the required labels (symbol, interval).")
                    return 1
                else:
                    print(f"\n❌ Test failed with ValueError: {e}")
                    raise
            except Exception as e:
                print(f"\n❌ Test failed with error: {e}")
                import traceback
                traceback.print_exc()
                return 1


def test_metric_definition():
    """Verifica que la definición de la métrica requiere los labels correctos."""
    print("Testing BINANCE_REQUEST_LATENCY metric definition...")
    
    # Verify labels are required
    try:
        BINANCE_REQUEST_LATENCY.observe(0.5)
        print("  ❌ ERROR: Metric should require labels but observe() worked without them")
        return 1
    except ValueError as e:
        if "missing label" in str(e).lower():
            print("  ✓ Metric correctly requires labels")
        else:
            print(f"  ❌ Unexpected ValueError: {e}")
            return 1
    
    # Verify labels work
    try:
        BINANCE_REQUEST_LATENCY.labels(symbol="BTCUSDT", interval="1h").observe(0.5)
        print("  ✓ Metric works correctly with labels")
        return 0
    except ValueError as e:
        print(f"  ❌ ERROR: Metric with labels raised ValueError: {e}")
        return 1


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Binance Client Metrics Test")
    print("=" * 60)
    print()
    
    # Test 1: Metric definition
    print("Test 1: Metric definition")
    print("-" * 60)
    result1 = test_metric_definition()
    print()
    
    # Test 2: get_klines metrics recording
    print("Test 2: get_klines metrics recording")
    print("-" * 60)
    result2 = await test_get_klines_metrics()
    print()
    
    # Summary
    print("=" * 60)
    if result1 == 0 and result2 == 0:
        print("✅ All tests passed!")
        return 0
    else:
        print("❌ Some tests failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

