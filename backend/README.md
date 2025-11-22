# One Smart Trade - Backend

Backend cuantitativo en FastAPI para análisis y recomendaciones de trading BTC.

## Setup

```bash
# Instalar Poetry si no está instalado
curl -sSL https://install.python-poetry.org | python3 -

# Instalar dependencias
poetry install

# Activar entorno virtual
poetry shell
```

## Ejecución

### Desarrollo

**Opción 1: Usar script (recomendado)**
```bash
# Windows PowerShell
.\start-dev.ps1

# Linux/Mac
./start-dev.sh
```

**Opción 2: Comando directo**
```bash
poetry run uvicorn app.main:app --reload --port 8000
```

El servidor estará disponible en `http://localhost:8000`. El frontend (Vite) está configurado para proxificar las peticiones `/api/*` a este puerto.

**Nota:** Asegúrate de que el backend esté corriendo antes de iniciar el frontend, de lo contrario verás errores `ECONNREFUSED` en la consola del navegador.

### Producción
```bash
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## Poblar Base de Datos

Si la base de datos está vacía, ejecuta el pipeline para poblar datos iniciales:

```bash
# Opción 1: Script directo
python scripts/populate_database.py

# Opción 2: Como módulo
poetry run python -m app.scripts.populate_database

# Opción 3: Via API (requiere ADMIN_API_KEY si está configurada)
curl -X POST "http://localhost:8000/api/v1/operational/trigger-pipeline" \
  -H "X-Admin-API-Key: your-key-here"
```

**Nota:** El pipeline se ejecuta automáticamente al iniciar el backend si:
- `AUTO_RUN_PIPELINE_ON_START=true` (habilitado por defecto en dev/demo) y no existe una recomendación para hoy, o
- No existe una recomendación para la fecha actual

Esto garantiza que `/api/v1/recommendation/today` devuelva datos inmediatamente después del inicio en entornos de desarrollo/demo, sin esperar al job programado de las 12:00 UTC. El job programado seguirá ejecutándose normalmente a las 12:00 UTC.

## Verificar Endpoints

Para verificar que los endpoints devuelven datos:

```bash
# Script de verificación
python scripts/verify_endpoints.py

# O manualmente:
curl http://localhost:8000/api/v1/recommendation/today
curl http://localhost:8000/api/v1/market/1h
```

## Testing

```bash
poetry run pytest
poetry run pytest --cov=app --cov-report=html
```

## Linting

```bash
poetry run ruff check .
poetry run ruff format .
poetry run mypy app
```

## Variables de Entorno

Crear `.env` en la raíz del backend:

```env
DATABASE_URL=sqlite:///./data/trading.db
BINANCE_API_BASE_URL=https://api.binance.com/api/v3
LOG_LEVEL=INFO
SCHEDULER_TIMEZONE=UTC
RECOMMENDATION_UPDATE_TIME=12:00
```

