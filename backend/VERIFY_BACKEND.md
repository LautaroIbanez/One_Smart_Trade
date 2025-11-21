# Verificación Rápida del Backend

## Comandos de Verificación

### 1. Verificar si el backend está corriendo

**Windows PowerShell:**
```powershell
Test-NetConnection -ComputerName localhost -Port 8000 -InformationLevel Quiet
```

**Linux/Mac:**
```bash
curl http://localhost:8000/health
# o
nc -z localhost 8000 && echo "Backend está corriendo" || echo "Backend NO está corriendo"
```

### 2. Probar una petición de ejemplo

**Windows PowerShell:**
```powershell
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/recommendation/today" -UseBasicParsing
```

**Linux/Mac:**
```bash
curl http://localhost:8000/api/v1/recommendation/today
```

**En el navegador:**
- Health check: http://localhost:8000/health
- API Docs: http://localhost:8000/docs
- Endpoint de recomendación: http://localhost:8000/api/v1/recommendation/today

### 3. Verificar logs del backend

Si el backend está corriendo, deberías ver logs en la terminal donde lo iniciaste. Si no hay logs o el proceso se detuvo, revisa:

1. **Errores en la terminal** donde corre el backend
2. **Dependencias faltantes:** `poetry install`
3. **Base de datos:** Debe crearse automáticamente en `data/trading.db`

## Solución de Problemas

### Error: "Poetry no está instalado"

```powershell
# Windows (PowerShell)
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -

# Linux/Mac
curl -sSL https://install.python-poetry.org | python3 -
```

### Error: "El puerto 8000 ya está en uso"

```powershell
# Windows: Encontrar proceso
netstat -ano | findstr :8000

# Linux/Mac: Encontrar proceso
lsof -i :8000
```

Luego detén el proceso o cambia el puerto en `vite.config.ts` y en el comando de uvicorn.

### Error: "ModuleNotFoundError" o errores de importación

```bash
cd backend
poetry install
```

### El backend se inicia pero se cae inmediatamente

1. Revisa los logs en la terminal
2. Verifica que no haya errores de sintaxis
3. Verifica que las dependencias estén instaladas
4. Los errores de métricas ya están corregidos, pero si persisten, revisa los logs

