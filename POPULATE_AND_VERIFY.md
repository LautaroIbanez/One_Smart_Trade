# Guía: Poblar Base de Datos y Verificar Endpoints

## Problema

Las pantallas del frontend están vacías con errores en rojo porque:
1. El backend no está corriendo, o
2. La base de datos está vacía (no hay datos ingeridos)

## Solución Paso a Paso

### Paso 1: Iniciar el Backend

Abre una terminal y ejecuta:

```powershell
cd backend
.\start-dev.ps1
```

O si Poetry no está en PATH:

```powershell
cd backend
poetry shell
uvicorn app.main:app --reload --port 8000
```

**Espera a ver:**
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

### Paso 2: Verificar que el Backend Está Corriendo

En otra terminal:

```powershell
# Verificar health
Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing

# O en el navegador:
# http://localhost:8000/docs
```

Deberías ver: `{"status": "healthy"}`

### Paso 3: Poblar la Base de Datos

El backend intentará poblar la base automáticamente al iniciar si está vacía. Si no, ejecuta manualmente:

```powershell
cd backend
python scripts/populate_database.py
```

O:

```powershell
poetry run python -m app.scripts.populate_database
```

**Este proceso:**
- Ingesta datos de Binance para todos los intervalos (15m, 30m, 1h, 4h, 1d, 1w)
- Cura los datos
- Genera una recomendación/señal

**Puede tomar varios minutos** dependiendo de la cantidad de datos a ingerir.

### Paso 4: Verificar Endpoints

Ejecuta el script de verificación:

```powershell
cd backend
python scripts/verify_endpoints.py
```

O verifica manualmente:

```powershell
# Recomendación
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/recommendation/today" -UseBasicParsing

# Mercado
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/market/1h" -UseBasicParsing
```

**Resultados esperados:**
- `/api/v1/recommendation/today`: Debe devolver una recomendación con `signal: "BUY"|"SELL"|"HOLD"` o `status: "no_data"` si no hay datos aún
- `/api/v1/market/1h`: Debe devolver datos de mercado con `status: "success"` y un array `data`

### Paso 5: Refrescar el Frontend

1. Si el frontend ya está corriendo, refresca la página (F5)
2. Si no está corriendo, inícialo:

```powershell
cd frontend
pnpm run dev
```

3. Abre http://localhost:5173 en el navegador

**Los paneles deberían mostrar:**
- ✅ Recomendación del día (en lugar de error rojo)
- ✅ Gráfico de precios (en lugar de error rojo)
- ✅ Datos de mercado (en lugar de error rojo)
- ✅ Métricas de riesgo (en lugar de error rojo)

## Solución de Problemas

### El backend se cae al iniciar

**Revisa los logs** en la terminal. Los errores de métricas ya están corregidos, pero si ves otros errores:

1. Verifica dependencias: `poetry install`
2. Verifica que la base de datos pueda crearse: `ls data/trading.db`
3. Revisa los logs para el error específico

### El pipeline falla durante la ingesta

**Causas comunes:**
- Problemas de conexión a Binance
- Rate limits de Binance
- Datos faltantes

**Solución:**
- El pipeline tiene manejo de errores y continuará con otros intervalos
- Revisa los logs para ver qué intervalos fallaron
- Puedes ejecutar el pipeline nuevamente

### Los endpoints devuelven "no_data"

**Causa:** La base de datos está vacía o el pipeline no completó.

**Solución:**
1. Ejecuta el pipeline manualmente: `python scripts/populate_database.py`
2. Verifica que el pipeline completó sin errores fatales
3. Espera a que el pipeline termine (puede tomar varios minutos)

### El frontend sigue mostrando errores

**Verifica:**
1. El backend está corriendo: `Test-NetConnection -ComputerName localhost -Port 8000`
2. Los endpoints devuelven datos: `python scripts/verify_endpoints.py`
3. El frontend está usando la URL correcta (verifica `vite.config.ts` o `.env`)

## Verificación Rápida

Ejecuta este comando para verificar todo de una vez:

```powershell
cd backend
python scripts/verify_endpoints.py
```

Este script verifica:
- ✅ Backend corriendo
- ✅ Endpoint de recomendación
- ✅ Endpoint de mercado
- ✅ Base de datos poblada

## Orden Completo

1. ✅ Iniciar backend: `.\start-dev.ps1`
2. ✅ Esperar a que el preflight complete (si está habilitado)
3. ✅ Poblar base de datos: `python scripts/populate_database.py` (si está vacía)
4. ✅ Verificar endpoints: `python scripts/verify_endpoints.py`
5. ✅ Iniciar frontend: `cd frontend && pnpm run dev`
6. ✅ Refrescar navegador en http://localhost:5173

