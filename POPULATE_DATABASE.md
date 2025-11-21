# Guía: Poblar Base de Datos y Verificar Endpoints

## Problema

Debido a los fallos anteriores de métricas, la ingesta inicial no completó y la base de datos quedó vacía, por lo que la UI muestra errores "Internal Server Error" al no encontrar datos.

## Solución Paso a Paso

### Paso 1: Iniciar el Backend

**IMPORTANTE:** El backend debe estar corriendo antes de ejecutar el pipeline.

Abre una **Terminal 1** y ejecuta:

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

**Verificar que el backend está corriendo:**
```powershell
# En otra terminal
Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing
```

Deberías ver: `{"status": "healthy"}`

### Paso 2: Ejecutar el Pipeline para Poblar la Base de Datos

Abre una **Terminal 2** (deja la Terminal 1 corriendo) y ejecuta:

**Opción A: Script completo (recomendado)**
```powershell
cd backend
python scripts/populate_and_verify.py
```

Este script:
- Ejecuta el pipeline completo
- Verifica los endpoints automáticamente
- Proporciona un resumen del estado

**Opción B: Solo poblar datos**
```powershell
cd backend
python scripts/populate_database.py
```

**Opción C: Como módulo de Python**
```powershell
cd backend
poetry run python -m app.scripts.seed_initial_data
```

**Este proceso ejecuta:**
1. Ingestión de datos de Binance para todos los intervalos (15m, 30m, 1h, 4h, 1d, 1w)
2. Curación de datos
3. Generación de señal/recomendación

**⏱️ Tiempo estimado:** 5-15 minutos dependiendo de:
- La cantidad de datos a ingerir
- La velocidad de conexión a Binance
- El número de intervalos a procesar

**Durante la ejecución verás:**
- Progreso de ingesta por intervalo
- Procesamiento de datos
- Generación de señales

### Paso 3: Verificar que los Endpoints Devuelven Datos

**Opción A: Usar el script de verificación (si usaste Opción B en Paso 2)**
```powershell
cd backend
python scripts/verify_endpoints.py
```

**Opción B: Verificación manual**

```powershell
# Recomendación del día
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/recommendation/today" -UseBasicParsing | Select-Object -ExpandProperty Content

# Datos de mercado (1h)
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/market/1h" -UseBasicParsing | Select-Object -ExpandProperty Content
```

**Resultados esperados:**

✅ **Endpoint de recomendación (`/api/v1/recommendation/today`):**
- Debe devolver `200 OK` con JSON conteniendo:
  - `signal`: "BUY", "SELL", o "HOLD"
  - `confidence`: porcentaje de confianza
  - `timestamp`: fecha/hora de la recomendación

✅ **Endpoint de mercado (`/api/v1/market/1h`):**
- Debe devolver `200 OK` con JSON conteniendo:
  - `status`: "success"
  - `data`: array con datos de velas
  - `current_price`: precio actual de BTC

❌ **Si ves errores:**
- `400 Bad Request` o `503 Service Unavailable` con `"status": "no_data"` → La base de datos aún está vacía, espera a que el pipeline complete
- `ECONNREFUSED` → El backend no está corriendo, vuelve al Paso 1

### Paso 4: Refrescar el Frontend

1. **Si el frontend ya está corriendo:**
   - Refresca la página (F5 o Ctrl+R)
   - Los paneles deberían mostrar datos en lugar de errores rojos

2. **Si el frontend no está corriendo:**
   ```powershell
   cd frontend
   pnpm run dev
   ```
   Luego abre http://localhost:5173 en el navegador

**Verificación en el frontend:**
- ✅ Panel de recomendación muestra señal (BUY/SELL/HOLD)
- ✅ Gráfico de precios muestra datos
- ✅ Panel de mercado muestra información
- ✅ Métricas de riesgo se calculan correctamente
- ✅ No hay errores "Internal Server Error" en rojo

## Solución de Problemas

### El Pipeline Falla con Errores de Métricas

**Síntoma:** Ver `ValueError: histogram metric is missing label values`

**Solución:** Las correcciones ya están aplicadas. Si aún ves este error:
1. Verifica que estás usando la versión más reciente del código
2. Reinicia el backend
3. Ejecuta el script de validación:
   ```powershell
   cd backend
   python scripts/validate_backend_startup.py
   ```

### El Pipeline Tarda Mucho Tiempo

**Causa:** Ingesta de muchos datos históricos

**Solución:**
- Es normal que tome 5-15 minutos
- Puedes reducir el tiempo configurando `PRESTART_LOOKBACK_DAYS` en `backend/app/core/config.py` a un valor menor (p. ej. 7 días en lugar de 30)
- El pipeline procesa intervalos en paralelo cuando es posible

### Los Endpoints Devuelven "no_data"

**Causa:** El pipeline aún no completó o falló silenciosamente

**Solución:**
1. Verifica los logs del pipeline para errores
2. Espera a que el pipeline complete (puede tomar varios minutos)
3. Verifica que el backend siga corriendo
4. Ejecuta el pipeline nuevamente si es necesario

### El Frontend Sigue Mostrando Errores

**Causa:** El frontend está usando datos en caché o el backend no está accesible

**Solución:**
1. Verifica que el backend esté corriendo: `.\check-backend.ps1`
2. Verifica que los endpoints devuelvan datos: `python scripts/verify_endpoints.py`
3. Limpia la caché del navegador (Ctrl+Shift+Delete)
4. Refresca la página con Ctrl+F5 (hard refresh)
5. Verifica la consola del navegador (F12) para errores específicos

## Comandos Rápidos

### Todo en Uno (Backend Corriendo)

```powershell
# Terminal 1: Backend (debe estar corriendo)
cd backend
.\start-dev.ps1

# Terminal 2: Poblar y verificar
cd backend
python scripts/populate_and_verify.py
```

### Verificación Rápida

```powershell
# Verificar backend
.\check-backend.ps1

# Verificar endpoints
cd backend
python scripts/verify_endpoints.py
```

## Checklist Final

- [ ] Backend corriendo en `http://localhost:8000`
- [ ] Pipeline ejecutado y completado sin errores fatales
- [ ] Endpoint `/api/v1/recommendation/today` devuelve datos (200 OK con signal)
- [ ] Endpoint `/api/v1/market/1h` devuelve datos (200 OK con data)
- [ ] Frontend refrescado y mostrando datos
- [ ] No hay errores "Internal Server Error" en rojo
- [ ] Los paneles muestran información en lugar de errores

## Próximos Pasos

Una vez que la base de datos esté poblada:

1. **El backend ejecutará automáticamente:**
   - Preflight maintenance al iniciar (si está habilitado)
   - Pipeline diario a las 12:00 UTC (cron job)
   - Ingesta cada 15 minutos (cron job)

2. **Para poblar datos manualmente en el futuro:**
   - Usa el script: `python scripts/populate_database.py`
   - O el endpoint API: `POST /api/v1/operational/trigger-pipeline` (requiere `ADMIN_API_KEY`)

3. **Para verificar el estado:**
   - Script: `python scripts/verify_endpoints.py`
   - Health check: `http://localhost:8000/health`
   - API docs: `http://localhost:8000/docs`

