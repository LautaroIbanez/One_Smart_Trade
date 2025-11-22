# Cómo Iniciar el Backend

## ⚠️ Problema Actual

El backend no está corriendo, por lo que el frontend recibe errores `ECONNREFUSED` en todas las peticiones `/api/v1/*`.

## Solución Rápida

### Opción 1: Usar el Script (Recomendado)

**Windows PowerShell:**
```powershell
cd backend
.\start-dev.ps1
```

**Linux/Mac:**
```bash
cd backend
./start-dev.sh
```

### Opción 2: Comando Directo

```bash
cd backend
poetry run uvicorn app.main:app --reload --port 8000
```

### Opción 3: Si Poetry no está en PATH

**Opción A: Activar entorno virtual de Poetry**
```powershell
cd backend
poetry shell
uvicorn app.main:app --reload --port 8000
```

**Opción B: Usar Python directamente (si uvicorn está instalado)**
```powershell
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

**Opción C: Script simple (sin Poetry)**
```powershell
cd backend
.\start-backend-simple.ps1
```

## Verificación

Una vez iniciado, deberías ver:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

**Verifica que el backend responde:**
```powershell
# Windows PowerShell
Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing

# O en el navegador:
# http://localhost:8000/docs
```

## Si el Backend se Cae

Si el backend se cae por errores, verifica los logs. Los errores de métricas ya están corregidos, pero si ves errores:

1. **Revisa los logs** en la terminal donde corre el backend
2. **Verifica que las dependencias estén instaladas:**
   ```bash
   cd backend
   poetry install
   ```
3. **Verifica que la base de datos exista:**
   ```bash
   # La base de datos se crea automáticamente, pero verifica:
   ls data/trading.db
   ```

## Configuración del Frontend

El frontend está configurado para usar el proxy de Vite que redirige `/api/*` a `http://localhost:8000`.

**Si el backend corre en otro puerto/host:**

1. Crea `frontend/.env`:
   ```env
   VITE_API_BASE_URL=http://localhost:TU_PUERTO
   ```

2. Reinicia el servidor de desarrollo del frontend:
   ```bash
   cd frontend
   pnpm run dev
   ```

## Poblar Base de Datos

Después de iniciar el backend, si la base de datos está vacía, ejecuta el pipeline:

```bash
cd backend
python scripts/populate_database.py
# o
poetry run python -m app.scripts.populate_database
```

Esto ejecutará:
1. Ingestión de datos de Binance
2. Curación de datos
3. Generación de señal/recomendación

**Nota:** El pipeline se ejecuta automáticamente al iniciar si:
- `AUTO_RUN_PIPELINE_ON_START=true` (habilitado por defecto en dev/demo) y no existe una recomendación para hoy, o
- No existe una recomendación para la fecha actual

Esto garantiza que `/api/v1/recommendation/today` devuelva datos inmediatamente después del inicio en entornos de desarrollo/demo, sin esperar al job programado de las 12:00 UTC.

## Verificar que Todo Funciona

```bash
cd backend
python scripts/verify_endpoints.py
```

Este script verifica:
- ✅ Backend está corriendo
- ✅ Endpoint de recomendación devuelve datos
- ✅ Endpoint de mercado devuelve datos
- ✅ Base de datos está poblada

## Orden de Inicio

1. **Primero:** Inicia el backend (puerto 8000)
2. **Segundo:** Pobla la base de datos (si está vacía)
3. **Tercero:** Verifica endpoints con `verify_endpoints.py`
4. **Cuarto:** Inicia el frontend (puerto 5173)

El frontend necesita que el backend esté corriendo y tenga datos para funcionar correctamente.

