# Iniciar Backend y Frontend - Guía Completa

## ⚠️ Orden Importante

**El backend DEBE estar corriendo antes del frontend**, de lo contrario verás errores `ECONNREFUSED` y paneles vacíos.

## Paso 1: Iniciar el Backend

Abre una **Terminal 1** y ejecuta:

### Opción A: Script Automático (Recomendado)

```powershell
cd backend
.\start-dev.ps1
```

### Opción B: Comando Directo

```powershell
cd backend
poetry run uvicorn app.main:app --reload --port 8000
```

### Opción C: Si Poetry no está en PATH

```powershell
cd backend
poetry shell
uvicorn app.main:app --reload --port 8000
```

### Verificar que el Backend Está Corriendo

Deberías ver en la terminal:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

**Verificación rápida:**
```powershell
# En otra terminal
Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing
```

O abre en el navegador: http://localhost:8000/docs

## Paso 2: Iniciar el Frontend

Abre una **Terminal 2** (deja la Terminal 1 corriendo) y ejecuta:

```powershell
cd frontend
pnpm run dev
```

Deberías ver:
```
  VITE v5.x.x  ready in xxx ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
```

## Paso 3: Verificar que Todo Funciona

### Verificar Backend Directamente

```powershell
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/recommendation/today" -UseBasicParsing
```

**Resultado esperado:**
- `200 OK` con datos JSON, o
- `400/503` con mensaje (pero NO `ECONNREFUSED`)

### Verificar Frontend (a través del Proxy)

Con el frontend corriendo, prueba:

```powershell
Invoke-WebRequest -Uri "http://localhost:5173/api/v1/recommendation/today" -UseBasicParsing
```

**Resultado esperado:**
- `200 OK` con datos JSON, o
- `400/503` con mensaje (pero NO `ECONNREFUSED`)

### Verificar en el Navegador

1. Abre http://localhost:5173
2. Los paneles deberían cargar datos (no errores rojos)
3. Si ves errores `ECONNREFUSED`, el backend no está corriendo

## Si el Backend Corre en Otro Host/Puerto

### Configuración con VITE_API_BASE_URL

1. Crea `frontend/.env`:
```env
VITE_API_BASE_URL=http://TU_HOST:TU_PUERTO
```

2. Reinicia el servidor de desarrollo:
```powershell
# Detén el servidor (Ctrl+C) y reinicia
cd frontend
pnpm run dev
```

### Configuración con Proxy en vite.config.ts

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

## Solución de Problemas

### Error: "ECONNREFUSED" en el Frontend

**Causa:** El backend no está corriendo o no es accesible.

**Solución:**
1. Verifica que el backend esté corriendo:
   ```powershell
   Test-NetConnection -ComputerName localhost -Port 8000
   ```
2. Si el puerto está libre, inicia el backend (ver Paso 1)
3. Si el backend corre en otro puerto, configura `VITE_API_BASE_URL` o actualiza el proxy

### Error: "Poetry no está instalado"

**Solución:**
```powershell
# Windows (PowerShell)
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -
```

Luego reinicia la terminal y vuelve a intentar.

### Error: "El puerto 8000 ya está en uso"

**Solución:**
1. Encuentra el proceso:
   ```powershell
   netstat -ano | findstr :8000
   ```
2. Detén el proceso o cambia el puerto:
   - En `vite.config.ts`: `target: 'http://localhost:NUEVO_PUERTO'`
   - En el comando de uvicorn: `--port NUEVO_PUERTO`

### El Frontend Muestra Paneles Vacíos

**Causa:** El backend está corriendo pero no hay datos en la base de datos.

**Solución:**
1. Ejecuta el pipeline para poblar datos:
   ```powershell
   cd backend
   python scripts/populate_database.py
   ```
2. Espera a que complete (puede tomar varios minutos)
3. Refresca el frontend (F5)

## Checklist Final

- [ ] Backend corriendo en `http://localhost:8000`
- [ ] Backend responde a `/health` (200 OK)
- [ ] Frontend corriendo en `http://localhost:5173`
- [ ] Endpoint `/api/v1/recommendation/today` devuelve datos (no ECONNREFUSED)
- [ ] Frontend muestra datos en lugar de errores rojos
- [ ] Los paneles del dashboard se cargan correctamente

## Comandos Rápidos de Verificación

```powershell
# Verificar backend
Test-NetConnection -ComputerName localhost -Port 8000

# Health check
Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing

# Endpoint de recomendación
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/recommendation/today" -UseBasicParsing

# A través del proxy del frontend (con frontend corriendo)
Invoke-WebRequest -Uri "http://localhost:5173/api/v1/recommendation/today" -UseBasicParsing
```

