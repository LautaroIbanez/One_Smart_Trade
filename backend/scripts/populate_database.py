#!/usr/bin/env python3
"""
Script para poblar la base de datos ejecutando el pipeline diario.

Este script ejecuta el pipeline completo (ingestión → curación → generación de señal)
para poblar la base de datos con datos iniciales.

Uso:
    python scripts/populate_database.py
    # o
    poetry run python -m app.scripts.populate_database
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logging import setup_logging, logger
from app.main import job_daily_pipeline


async def main():
    """Ejecutar el pipeline diario para poblar la base de datos."""
    setup_logging()
    
    print("=" * 60)
    print("Poblando Base de Datos - Pipeline Diario")
    print("=" * 60)
    print()
    print("Este proceso ejecutará:")
    print("  1. Ingestión de datos de Binance para todos los intervalos")
    print("  2. Curación de datos")
    print("  3. Generación de señal/recomendación")
    print()
    print("Esto puede tomar varios minutos...")
    print()
    
    try:
        await job_daily_pipeline()
        print()
        print("=" * 60)
        print("✅ Pipeline completado exitosamente")
        print("=" * 60)
        print()
        print("La base de datos ahora tiene datos. Puedes:")
        print("  - Verificar endpoints: http://localhost:8000/api/v1/recommendation/today")
        print("  - Verificar mercado: http://localhost:8000/api/v1/market/1h")
        print("  - Refrescar el frontend para ver los datos")
        return 0
    except Exception as exc:
        print()
        print("=" * 60)
        print("❌ Pipeline falló")
        print("=" * 60)
        print()
        logger.error(f"Pipeline execution failed: {exc}", exc_info=True)
        print(f"Error: {exc}")
        print()
        print("Revisa los logs arriba para más detalles.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

