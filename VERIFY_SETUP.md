# Verificación y Configuración del Setup

## Estado Actual

El frontend está configurado para enviar peticiones `/api/v1/*` al backend mediante:
- **Proxy de Vite**: Redirige `/api/*` a `http://localhost:8000` (configurado en `vite.config.ts`)
- **Fallback**: Si `VITE_API_BASE_URL` está definida, se usa esa URL en lugar del proxy

## Verificación Rápida

### 1. Verificar Configuración del Frontend

```powershell
# Verificar vite.config.ts
cd frontend
Get-Content vite.config.ts | Select-String "proxy" -Context 5

# Verificar si hay .env
if (Test-Path .env) { Get-Content .env } else { Write-Host "No hay .env - usando proxy" }
```

**Configuración esperada:**
- `vite.config.ts` tiene `proxy: { '/api': { target: 'http://localhost:8000' } }`
- No hay `.env` (usa proxy) O `.env` tiene `VITE_API_BASE_URL=http://localhost:8000`

### 2. Verificar que el Backend Esté Corriendo

```powershell
# Verificar puerto 8000
Test-NetConnection -ComputerName localhost -Port 8000 -InformationLevel Quiet

# Probar endpoint
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 5 -UseBasicParsing
    Write-Host "✓ Backend responde: $($response.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "✗ Backend NO responde: $_" -ForegroundColor Red
}
```

### 3. Verificar Proxy del Frontend

Con el frontend corriendo (`pnpm dev`), prueba:

```powershell
# Desde el navegador o curl
curl http://localhost:5173/api/v1/recommendation/today
```

**Resultado esperado:**
- Si el backend está corriendo: Respuesta 200 o 400/503 (pero NO ECONNREFUSED)
- Si el backend NO está corriendo: ECONNREFUSED o timeout

## Solución: Iniciar el Backend

### Opción 1: Con Poetry (Recomendado)

```powershell
cd backend
poetry run uvicorn app.main:app --reload --port 8000
```

### Opción 2: Activar Entorno Virtual Primero

```powershell
cd backend
poetry shell
uvicorn app.main:app --reload --port 8000
```

### Opción 3: Python Directo (si uvicorn está instalado)

```powershell
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

### Opción 4: Script de Inicio

```powershell
cd backend
.\start-dev.ps1
```

## Si el Backend Corre en Otro Host/Puerto

### Opción A: Usar VITE_API_BASE_URL

1. Crea `frontend/.env`:
```env
VITE_API_BASE_URL=http://TU_HOST:TU_PUERTO
```

2. Reinicia el servidor de desarrollo:
```powershell
cd frontend
# Detén el servidor (Ctrl+C) y reinicia
pnpm run dev
```

### Opción B: Cambiar Proxy en vite.config.ts

Edita `frontend/vite.config.ts`:

```typescript
server: {
  port: 5173,
  proxy: {
    '/api': {
      target: 'http://TU_HOST:TU_PUERTO',  // Cambia aquí
      changeOrigin: true,
    },
  },
},
```

Luego reinicia `pnpm dev`.

## Verificación Final

Una vez que el backend esté corriendo:

```powershell
# 1. Verificar backend directamente
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/recommendation/today" -UseBasicParsing

# 2. Verificar a través del proxy del frontend (con frontend corriendo)
Invoke-WebRequest -Uri "http://localhost:5173/api/v1/recommendation/today" -UseBasicParsing

# 3. Verificar en el navegador
# Abre: http://localhost:5173
# Los paneles deberían cargar datos en lugar de errores rojos
```

## Checklist

- [ ] Backend corriendo en `http://localhost:8000`
- [ ] Backend responde a `/health`
- [ ] Frontend corriendo en `http://localhost:5173`
- [ ] `vite.config.ts` tiene proxy configurado a `http://localhost:8000`
- [ ] Si usas otro host, `VITE_API_BASE_URL` está definida en `.env`
- [ ] Endpoint `/api/v1/recommendation/today` devuelve datos (200 o 400/503, no ECONNREFUSED)
- [ ] Frontend muestra datos en lugar de errores rojos

