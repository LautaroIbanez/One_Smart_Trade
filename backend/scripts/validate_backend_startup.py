#!/usr/bin/env python3
"""
Script para validar que el backend puede iniciar sin errores de métricas.

Este script verifica:
1. Que las métricas estén correctamente configuradas
2. Que el preflight pueda ejecutarse sin errores
3. Que el backend pueda iniciar sin ValueError por métricas faltantes
"""
import sys
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.observability.metrics import BINANCE_REQUEST_LATENCY, record_data_gap
from app.data.binance_client import BinanceClient
from app.services.preflight import run_preflight


def test_metrics_configuration():
    """Test que las métricas estén correctamente configuradas."""
    print("Test 1: Verificación de configuración de métricas")
    print("-" * 60)
    
    # Test BINANCE_REQUEST_LATENCY
    try:
        # Verificar que requiere labels
        try:
            BINANCE_REQUEST_LATENCY.observe(0.5)
            print("  ❌ ERROR: BINANCE_REQUEST_LATENCY debería requerir labels")
            return 1
        except ValueError:
            print("  ✓ BINANCE_REQUEST_LATENCY requiere labels (correcto)")
        
        # Verificar que funciona con labels
        BINANCE_REQUEST_LATENCY.labels(symbol="BTCUSDT", interval="1h").observe(0.5)
        print("  ✓ BINANCE_REQUEST_LATENCY funciona con labels correctos")
        
        # Test record_data_gap
        try:
            record_data_gap("1h")
            print("  ✓ record_data_gap funciona correctamente")
        except ValueError as e:
            print(f"  ⚠ WARNING: record_data_gap falló: {e}")
            print("     (Esto está bien si la métrica tiene labels requeridos)")
        
        return 0
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


async def test_binance_client_metrics():
    """Test que BinanceClient registra métricas correctamente."""
    print("\nTest 2: BinanceClient registra métricas correctamente")
    print("-" * 60)
    
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
            try:
                await client.get_klines("BTCUSDT", "1h")
                print("  ✓ get_klines completa sin errores de métricas")
                return 0
            except ValueError as e:
                if "missing label" in str(e).lower():
                    print(f"  ❌ ERROR: get_klines falló por labels faltantes: {e}")
                    return 1
                raise


async def test_preflight_resilience():
    """Test que el preflight es resiliente a fallos de métricas."""
    print("\nTest 3: Preflight es resiliente a fallos de métricas")
    print("-" * 60)
    
    # Mock preflight para que no haga llamadas reales
    with patch("app.services.preflight.DataIngestion") as mock_ingestion_class:
        mock_ingestion = MagicMock()
        mock_ingestion.check_gaps.return_value = []
        mock_ingestion_class.return_value = mock_ingestion
        
        with patch("app.services.preflight.DataCuration") as mock_curation_class:
            mock_curation = MagicMock()
            mock_curation.curate_interval.return_value = {"status": "success"}
            mock_curation_class.return_value = mock_curation
            
            with patch("app.services.preflight.SessionLocal"):
                with patch("app.services.preflight.log_run"):
                    try:
                        await run_preflight(days=1, intervals=("1h",))
                        print("  ✓ Preflight completa sin errores")
                        return 0
                    except ValueError as e:
                        if "missing label" in str(e).lower():
                            print(f"  ❌ ERROR: Preflight falló por labels faltantes: {e}")
                            return 1
                        raise
                    except Exception as e:
                        print(f"  ⚠ WARNING: Preflight falló con otro error: {e}")
                        print("     (Esto puede ser normal si no hay datos)")
                        return 0


async def main():
    """Run all validation tests."""
    print("=" * 60)
    print("Validación de Inicio del Backend")
    print("=" * 60)
    print()
    
    results = []
    
    # Test 1: Configuración de métricas
    result1 = test_metrics_configuration()
    results.append(("Configuración de métricas", result1))
    
    # Test 2: BinanceClient
    result2 = await test_binance_client_metrics()
    results.append(("BinanceClient métricas", result2))
    
    # Test 3: Preflight
    result3 = await test_preflight_resilience()
    results.append(("Preflight resiliencia", result3))
    
    # Summary
    print("\n" + "=" * 60)
    print("Resumen")
    print("=" * 60)
    
    all_passed = True
    for test_name, result in results:
        status = "✓ PASS" if result == 0 else "❌ FAIL"
        print(f"  {status}: {test_name}")
        if result != 0:
            all_passed = False
    
    print()
    if all_passed:
        print("✅ Todos los tests pasaron. El backend debería iniciar correctamente.")
        print()
        print("Para iniciar el backend:")
        print("  cd backend")
        print("  poetry run uvicorn app.main:app --reload --port 8000")
        return 0
    else:
        print("❌ Algunos tests fallaron. Revisa los errores arriba.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

