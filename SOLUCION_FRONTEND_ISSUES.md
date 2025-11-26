# Solución: Frontend sin datos / timeouts

## 📊 Diagnóstico Actual

Basado en el análisis del runbook `frontend_no_data.md`, aquí está el estado de tu aplicación:

### ✅ Estado Actual
- **Base de datos:** Existe (`trading.db`, 880 KB, última modificación: 24/11/2025)
- **Datos curados:** Disponibles (tanto estructura legacy como particionada)
  - ✓ `data/curated/1d/latest.parquet` existe
  - ✓ `data/curated/binance/BTCUSDT/1d/latest.parquet` existe
- **Scripts de diagnóstico:** Disponibles y funcionando

### ❌ Problemas Detectados
- **Backend NO está corriendo** en `http://localhost:8000`
- **Frontend no puede conectarse** porque el backend está apagado

## 🔧 Solución Paso a Paso

### Paso 1: Iniciar el Backend

Abre una terminal PowerShell y ejecuta:

```powershell
cd backend
.\start-dev.ps1
```

**O si prefieres ejecutar manualmente:**

```powershell
cd backend
poetry run uvicorn app.main:app --reload --port 8000
```

**Espera a ver:**
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

### Paso 2: Verificar que el Backend Está Corriendo

En otra terminal PowerShell (deja la primera corriendo):

```powershell
Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing
```

**Deberías ver:** `{"status": "healthy"}`

### Paso 3: Verificar el Estado del Pipeline

El backend ejecutará automáticamente el pipeline inicial si no hay recomendación para hoy. Verifica el estado:

```powershell
$response = Invoke-WebRequest -Uri "http://localhost:8000/api/v1/recommendation/today" -UseBasicParsing
Write-Host "Status: $($response.StatusCode)"
$json = $response.Content | ConvertFrom-Json
$json | ConvertTo-Json -Depth 3
```

**Posibles respuestas:**
- **200 OK:** Hay datos disponibles ✓
- **202 Processing:** El pipeline está corriendo (espera y reintenta)
- **400/503:** Revisa el mensaje de error en el JSON

### Paso 4: Verificar Endpoints Completos

Ejecuta el script de verificación:

```powershell
cd backend
python scripts\verify_endpoints.py
```

Este script verifica:
- ✓ Backend corriendo
- ✓ Endpoint de recomendación
- ✓ Endpoint de mercado
- ✓ Base de datos poblada

### Paso 5: Configurar el Frontend (si es necesario)

**Si el backend NO está en `localhost:8000`:**

1. Crea `frontend/.env`:
   ```env
   VITE_API_BASE_URL=http://TU_HOST:TU_PUERTO
   ```

2. Reinicia el servidor de desarrollo del frontend:
   ```powershell
   cd frontend
   pnpm run dev
   ```

**Si el frontend corre en un puerto diferente (5174, 5175, 8080, etc.):**

1. Añade el puerto a `backend/.env`:
   ```env
   CORS_ORIGINS=["http://localhost:5173","http://localhost:TU_PUERTO"]
   ```

2. Reinicia el backend

### Paso 6: Iniciar el Frontend

En otra terminal:

```powershell
cd frontend
pnpm run dev
```

El frontend estará disponible en `http://localhost:5173`

## 🚀 Script de Diagnóstico Automático

He creado un script de diagnóstico que puedes ejecutar:

```powershell
cd backend
.\scripts\diagnose_frontend_issues.ps1
```

Este script verifica automáticamente:
- Estado del backend
- Estado del pipeline
- Disponibilidad de datos
- Configuración del frontend
- Configuración CORS

## ⚠️ Notas Importantes

### Comportamiento del Pipeline Inicial

- El backend ejecuta automáticamente el pipeline al iniciar si:
  - `AUTO_RUN_PIPELINE_ON_START=True` (por defecto en dev)
  - No hay recomendación para el día actual

- El pipeline se ejecuta en **background** (no bloquea el servidor)
- Los endpoints devuelven **HTTP 202** mientras el pipeline corre
- El frontend maneja automáticamente los 202 con reintentos

### Si el Pipeline Tarda Mucho

El pipeline puede tardar varios minutos en:
1. Ingerir datos de Binance (todos los intervalos)
2. Curar los datos
3. Generar la recomendación

**Mientras tanto:**
- Los endpoints devolverán 202 (processing)
- El frontend mostrará "procesando" en lugar de timeout
- No necesitas hacer nada, solo esperar

### Verificar Progreso del Pipeline

Puedes verificar el progreso consultando el endpoint:

```powershell
$response = Invoke-WebRequest -Uri "http://localhost:8000/api/v1/recommendation/today" -UseBasicParsing
$json = $response.Content | ConvertFrom-Json
if ($json.pipeline) {
    Write-Host "Pipeline running: $($json.pipeline.running)"
    Write-Host "Started at: $($json.pipeline.started_at)"
    Write-Host "Completed at: $($json.pipeline.completed_at)"
}
```

## ✅ Puntos de Salida (Verificación Final)

Una vez que todo esté funcionando:

- ✅ Backend responde 200 en `/health`
- ✅ `/api/v1/recommendation/today` devuelve 200 con JSON válido (no 202, no timeout)
- ✅ Frontend muestra paneles con datos (automáticamente o tras un refresco)

## 🔍 Si Aún Tienes Problemas

1. **Ejecuta el script de diagnóstico:**
   ```powershell
   cd backend
   .\scripts\diagnose_frontend_issues.ps1
   ```

2. **Verifica los logs del backend** para ver errores específicos

3. **Revisa DevTools > Network** en el navegador para ver:
   - A qué URL están yendo las peticiones
   - Qué códigos de estado están recibiendo
   - Si hay errores CORS

4. **Si la base de datos está vacía:**
   ```powershell
   cd backend
   python scripts\populate_database.py
   ```

## 📝 Orden Recomendado de Inicio

1. **Primero:** Inicia el backend (`.\start-dev.ps1`)
2. **Segundo:** Espera a ver "Application startup complete"
3. **Tercero:** Verifica endpoints con `python scripts\verify_endpoints.py`
4. **Cuarto:** Inicia el frontend (`pnpm run dev` en frontend/)
5. **Quinto:** Abre el navegador en `http://localhost:5173`

El frontend necesita que el backend esté corriendo y tenga datos para funcionar correctamente.

