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

