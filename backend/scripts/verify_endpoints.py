#!/usr/bin/env python3
"""
Script para verificar que los endpoints del backend devuelven datos.

Este script verifica que:
1. El backend esté corriendo
2. Los endpoints principales devuelvan datos
3. La base de datos esté poblada

Uso:
    python scripts/verify_endpoints.py
"""
import sys
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import httpx
except ImportError:
    print("ERROR: httpx no está instalado. Instala con: pip install httpx")
    sys.exit(1)


def check_backend_running():
    """Verificar que el backend esté corriendo."""
    print("1. Verificando que el backend esté corriendo...")
    try:
        response = httpx.get("http://localhost:8000/health", timeout=5.0)
        if response.status_code == 200:
            print("   ✓ Backend está corriendo")
            return True
        else:
            print(f"   ❌ Backend responde con código {response.status_code}")
            return False
    except httpx.ConnectError:
        print("   ❌ Backend NO está corriendo en http://localhost:8000")
        print("      Inicia el backend con: poetry run uvicorn app.main:app --reload --port 8000")
        return False
    except Exception as e:
        print(f"   ❌ Error al conectar: {e}")
        return False


def check_recommendation_endpoint():
    """Verificar el endpoint de recomendación."""
    print("\n2. Verificando /api/v1/recommendation/today...")
    try:
        response = httpx.get("http://localhost:8000/api/v1/recommendation/today", timeout=30.0)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get("signal") in ("BUY", "SELL", "HOLD"):
                print(f"   ✓ Endpoint devuelve recomendación: {data.get('signal')}")
                print(f"   ✓ Confianza: {data.get('confidence', 'N/A')}%")
                return True
            elif data.get("status") == "no_data":
                print("   ⚠ Endpoint responde pero no hay datos (status: no_data)")
                print("      Ejecuta el pipeline para poblar datos: python scripts/populate_database.py")
                return False
            else:
                print(f"   ⚠ Respuesta inesperada: {data.get('status', 'unknown')}")
                return False
        elif response.status_code == 400:
            data = response.json()
            detail = data.get("detail", {})
            if isinstance(detail, dict) and detail.get("status") == "capital_missing":
                print("   ⚠ Capital no configurado (esto es normal en desarrollo)")
                print("      El endpoint funciona pero requiere capital para generar señales")
                return True  # El endpoint funciona, solo necesita capital
            else:
                print(f"   ❌ Error 400: {detail}")
                return False
        else:
            print(f"   ❌ Error {response.status_code}: {response.text[:200]}")
            return False
    except httpx.TimeoutException:
        print("   ❌ Timeout esperando respuesta (el backend puede estar procesando)")
        return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def check_market_endpoint():
    """Verificar el endpoint de mercado."""
    print("\n3. Verificando /api/v1/market/1h...")
    try:
        response = httpx.get("http://localhost:8000/api/v1/market/1h", timeout=30.0)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success" and data.get("data"):
                print(f"   ✓ Endpoint devuelve datos de mercado")
                print(f"   ✓ Precio actual: ${data.get('current_price', 'N/A'):,.2f}" if data.get('current_price') else "   ✓ Datos disponibles")
                return True
            elif data.get("status") == "no_data":
                print("   ⚠ Endpoint responde pero no hay datos de mercado")
                print("      Ejecuta el pipeline para poblar datos: python scripts/populate_database.py")
                return False
            else:
                print(f"   ⚠ Respuesta inesperada: {data.get('status', 'unknown')}")
                return False
        else:
            print(f"   ❌ Error {response.status_code}: {response.text[:200]}")
            return False
    except httpx.TimeoutException:
        print("   ❌ Timeout esperando respuesta")
        return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def check_database_populated():
    """Verificar que la base de datos tenga datos."""
    print("\n4. Verificando que la base de datos esté poblada...")
    try:
        from app.core.database import SessionLocal
        from app.db.models import RecommendationORM
        from sqlalchemy import func, select
        
        db = SessionLocal()
        try:
            count_stmt = select(func.count(RecommendationORM.id))
            count = db.execute(count_stmt).scalar() or 0
            
            if count > 0:
                print(f"   ✓ Base de datos tiene {count} recomendación(es)")
                return True
            else:
                print("   ⚠ Base de datos está vacía (no hay recomendaciones)")
                print("      Ejecuta el pipeline para poblar datos: python scripts/populate_database.py")
                return False
        finally:
            db.close()
    except Exception as e:
        print(f"   ⚠ No se pudo verificar la base de datos: {e}")
        return False


def main():
    """Ejecutar todas las verificaciones."""
    print("=" * 60)
    print("Verificación de Endpoints del Backend")
    print("=" * 60)
    print()
    
    results = []
    
    # Check 1: Backend running
    backend_running = check_backend_running()
    results.append(("Backend corriendo", backend_running))
    
    if not backend_running:
        print("\n" + "=" * 60)
        print("❌ El backend no está corriendo. Inicia el backend primero.")
        print("=" * 60)
        return 1
    
    # Check 2: Recommendation endpoint
    rec_ok = check_recommendation_endpoint()
    results.append(("Endpoint de recomendación", rec_ok))
    
    # Check 3: Market endpoint
    market_ok = check_market_endpoint()
    results.append(("Endpoint de mercado", market_ok))
    
    # Check 4: Database populated
    db_ok = check_database_populated()
    results.append(("Base de datos poblada", db_ok))
    
    # Summary
    print("\n" + "=" * 60)
    print("Resumen")
    print("=" * 60)
    
    all_ok = True
    for check_name, result in results:
        status = "✓ OK" if result else "⚠ FALTA"
        print(f"  {status}: {check_name}")
        if not result:
            all_ok = False
    
    print()
    if all_ok:
        print("✅ Todos los checks pasaron. El frontend debería mostrar datos.")
        print()
        print("Próximos pasos:")
        print("  1. Refresca el frontend en http://localhost:5173")
        print("  2. Los paneles deberían mostrar información en lugar de errores")
        return 0
    else:
        print("⚠ Algunos checks fallaron. Acciones recomendadas:")
        print()
        if not db_ok or (not rec_ok and not market_ok):
            print("  Para poblar la base de datos:")
            print("    cd backend")
            print("    python scripts/populate_database.py")
            print("    # o")
            print("    poetry run python -m app.scripts.populate_database")
        print()
        print("  Luego vuelve a ejecutar este script para verificar.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

