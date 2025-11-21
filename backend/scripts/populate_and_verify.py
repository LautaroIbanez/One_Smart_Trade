#!/usr/bin/env python3
"""
Script completo para poblar la base de datos y verificar endpoints.

Este script:
1. Ejecuta el pipeline diario para poblar la base de datos
2. Verifica que los endpoints devuelven datos
3. Proporciona un resumen del estado

Uso:
    python scripts/populate_and_verify.py
    # o
    poetry run python -m app.scripts.populate_and_verify
"""
import asyncio
import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logging import setup_logging, logger
from app.main import job_daily_pipeline


async def check_endpoint(url: str, description: str) -> tuple[bool, str]:
    """Check if an endpoint returns data."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                # Check if response has actual data
                if isinstance(data, dict):
                    if "status" in data and data["status"] == "no_data":
                        return False, f"Endpoint responde pero no hay datos (status: no_data)"
                    if "signal" in data or "data" in data or "recommendation" in data:
                        return True, f"OK - Endpoint devuelve datos"
                return True, f"OK - Status {response.status_code}"
            elif response.status_code in (400, 503):
                return False, f"Endpoint responde pero no hay datos (status: {response.status_code})"
            else:
                return False, f"Error: Status {response.status_code}"
    except httpx.ConnectError:
        return False, "Error: Backend no está corriendo (ECONNREFUSED)"
    except httpx.TimeoutException:
        return False, "Error: Timeout esperando respuesta"
    except Exception as e:
        return False, f"Error: {str(e)}"


async def verify_endpoints(base_url: str = "http://localhost:8000") -> dict[str, tuple[bool, str]]:
    """Verify that endpoints return data."""
    endpoints = {
        "recommendation": f"{base_url}/api/v1/recommendation/today",
        "market_1h": f"{base_url}/api/v1/market/1h",
        "health": f"{base_url}/health",
    }
    
    results = {}
    for name, url in endpoints.items():
        if name == "recommendation":
            desc = "Recomendación del día"
        elif name == "market_1h":
            desc = "Datos de mercado (1h)"
        else:
            desc = "Health check"
        
        success, message = await check_endpoint(url, desc)
        results[name] = (success, message)
    
    return results


async def main():
    """Ejecutar pipeline y verificar endpoints."""
    setup_logging()
    
    print("=" * 70)
    print("Poblar Base de Datos y Verificar Endpoints")
    print("=" * 70)
    print()
    
    # Step 1: Run pipeline
    print("Paso 1: Ejecutando pipeline diario...")
    print("-" * 70)
    print("Este proceso ejecutará:")
    print("  1. Ingestión de datos de Binance para todos los intervalos")
    print("  2. Curación de datos")
    print("  3. Generación de señal/recomendación")
    print()
    print("Esto puede tomar varios minutos...")
    print()
    
    pipeline_start = time.time()
    try:
        await job_daily_pipeline()
        pipeline_duration = time.time() - pipeline_start
        print()
        print("✓ Pipeline completado exitosamente")
        print(f"  Duración: {pipeline_duration:.1f} segundos")
        print()
    except Exception as exc:
        pipeline_duration = time.time() - pipeline_start
        print()
        print("✗ Pipeline falló")
        print(f"  Duración: {pipeline_duration:.1f} segundos")
        print(f"  Error: {exc}")
        print()
        logger.error(f"Pipeline execution failed: {exc}", exc_info=True)
        print("Continuando con verificación de endpoints...")
        print()
    
    # Step 2: Verify endpoints
    print("Paso 2: Verificando endpoints...")
    print("-" * 70)
    
    # Wait a bit for any async operations to complete
    await asyncio.sleep(2)
    
    results = await verify_endpoints()
    
    print()
    for name, (success, message) in results.items():
        status = "✓" if success else "✗"
        print(f"  {status} {name:20s}: {message}")
    
    print()
    print("=" * 70)
    
    # Summary
    all_ok = all(success for success, _ in results.values())
    pipeline_ok = "pipeline_start" in locals() and "exc" not in locals()
    
    if all_ok and pipeline_ok:
        print("✅ ÉXITO: Base de datos poblada y endpoints funcionando")
        print("=" * 70)
        print()
        print("Próximos pasos:")
        print("  1. Refresca el frontend (F5) para ver los datos")
        print("  2. Verifica que los paneles muestran información")
        print("  3. Los errores 'Internal Server Error' deberían desaparecer")
        return 0
    elif pipeline_ok:
        print("⚠️  ADVERTENCIA: Pipeline completó pero algunos endpoints no tienen datos")
        print("=" * 70)
        print()
        print("Posibles causas:")
        print("  - El pipeline completó pero no generó recomendación")
        print("  - Los datos aún se están procesando")
        print("  - Espera unos minutos y vuelve a verificar")
        return 1
    else:
        print("❌ ERROR: Pipeline falló o endpoints no responden")
        print("=" * 70)
        print()
        print("Revisa:")
        print("  1. Que el backend esté corriendo: http://localhost:8000/health")
        print("  2. Los logs del backend para errores")
        print("  3. La conexión a Binance (para ingesta de datos)")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

