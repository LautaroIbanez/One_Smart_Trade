# Inicio Rápido - One Smart Trade

## ⚠️ Importante: Orden de Inicio

El **backend debe estar corriendo** antes de iniciar el frontend, de lo contrario verás errores `ECONNREFUSED` y paneles vacíos en la UI.

**Si ves errores ECONNREFUSED:** El backend no está corriendo. Ver `START_BACKEND.md` para instrucciones detalladas.

## Pasos para Iniciar

### 1. Iniciar el Backend (Terminal 1)

```bash
cd backend

# Opción A: Usar script (Windows PowerShell)
.\start-dev.ps1

# Opción B: Usar script (Linux/Mac)
./start-dev.sh

# Opción C: Comando directo
poetry run uvicorn app.main:app --reload --port 8000
```

**Verificar que el backend está corriendo:**
- Deberías ver: `Uvicorn running on http://127.0.0.1:8000`
- Puedes verificar en el navegador: http://localhost:8000/docs

### 2. Iniciar el Frontend (Terminal 2)

```bash
cd frontend
pnpm run dev
```

El frontend estará disponible en `http://localhost:5173`

**Nota:** Si el backend corre en otro host/puerto (no localhost:8000), crea un archivo `.env` en `frontend/` con:
```env
VITE_API_BASE_URL=http://TU_BACKEND_URL
```
Luego reinicia el servidor de desarrollo.

## Solución de Problemas

### Error: "ECONNREFUSED" o paneles vacíos

**Causa:** El backend no está corriendo o no es accesible en la URL configurada.

**Solución:**
1. Verifica que el backend esté corriendo: `Test-NetConnection -ComputerName localhost -Port 8000` (Windows) o `curl http://localhost:8000/health` (Linux/Mac)
2. Si el puerto está ocupado, detén el proceso que lo está usando
3. **Si el backend corre en otro host/puerto:**
   - Crea un archivo `.env` en `frontend/` (copia de `.env.example`)
   - Define `VITE_API_BASE_URL` con la URL del backend:
     ```env
     VITE_API_BASE_URL=http://localhost:TU_PUERTO
     # o
     VITE_API_BASE_URL=https://api.example.com
     ```
   - Reinicia el servidor de desarrollo (`pnpm run dev`)

### Error: "Poetry no está instalado"

**Solución:**
```bash
# Windows (PowerShell)
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -

# Linux/Mac
curl -sSL https://install.python-poetry.org | python3 -
```

### Error: "El puerto 8000 ya está en uso"

**Solución:**
1. Encuentra el proceso: `netstat -ano | findstr :8000` (Windows) o `lsof -i :8000` (Linux/Mac)
2. Detén el proceso o cambia el puerto en `vite.config.ts` y en el comando de uvicorn

## Verificación Final

### Verificar Backend

```powershell
# Health check
Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing

# Endpoint de recomendación
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/recommendation/today" -UseBasicParsing

# O en el navegador:
# http://localhost:8000/docs (API docs)
```

### Verificar Frontend (con Backend Corriendo)

```powershell
# A través del proxy de Vite
Invoke-WebRequest -Uri "http://localhost:5173/api/v1/recommendation/today" -UseBasicParsing

# O en el navegador:
# http://localhost:5173
```

### Checklist

1. ✅ Backend corriendo en http://localhost:8000
2. ✅ Backend responde a `/health` y `/api/v1/recommendation/today`
3. ✅ Frontend corriendo en http://localhost:5173
4. ✅ Puedes acceder a http://localhost:8000/docs (API docs del backend)
5. ✅ Puedes acceder a http://localhost:5173 (UI del frontend)
6. ✅ Los paneles del dashboard se cargan correctamente (no errores ECONNREFUSED)
7. ✅ Los endpoints devuelven datos (200 o 400/503, no ECONNREFUSED)

