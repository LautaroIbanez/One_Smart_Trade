# Guía de Instalación - One Smart Trade

## Requisitos Previos

### Sistema Operativo
- Linux (Ubuntu 20.04+, Debian 11+, etc.)
- macOS 10.15+
- Windows 10/11 (con WSL2 recomendado)

### Software Requerido

1. **Python 3.11 o 3.12**
   ```bash
   python3 --version
   ```

2. **Node.js 20+**
   ```bash
   node --version
   ```

3. **Poetry** (gestión de dependencias Python)
   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   ```

4. **pnpm** (gestión de dependencias Node)
   ```bash
   npm install -g pnpm
   ```

## Instalación Manual

### 1. Clonar el Repositorio

```bash
git clone <repository-url>
cd "One Smart Trade"
```

### 2. Configurar Backend

```bash
cd backend

# Instalar dependencias
poetry install

# Crear archivo de configuración
cp .env.example .env

# Editar .env según necesidad
nano .env
```

**Variables de entorno importantes (backend/.env):**
- `DATABASE_URL`: URL de la base de datos (por defecto SQLite)
- `BINANCE_API_BASE_URL`: URL base de la API de Binance
- `LOG_LEVEL`: Nivel de logging (INFO, DEBUG, etc.)
- `RECOMMENDATION_UPDATE_TIME`: Hora de actualización diaria (formato HH:MM)

Ejemplo:
```env
DATABASE_URL=sqlite:///./data/trading.db
BINANCE_API_BASE_URL=https://api.binance.com/api/v3
LOG_LEVEL=INFO
SCHEDULER_TIMEZONE=UTC
RECOMMENDATION_UPDATE_TIME=12:00
```

### 3. Configurar Frontend

```bash
cd ../frontend

# Instalar dependencias
pnpm install

# Crear archivo de configuración (opcional)
echo "VITE_API_BASE_URL=http://localhost:8000" > .env.local
```

### 4. Crear Directorios de Datos

```bash
cd ../backend
mkdir -p data/raw data/curated
```

## Ejecución

### Modo Desarrollo

**Terminal 1 - Backend:**
```bash
cd backend
poetry run uvicorn app.main:app --reload --port 8000
```

**Terminal 2 - Frontend:**
```bash
cd frontend
pnpm run dev
```

Acceder a: http://localhost:5173

### Modo Producción

#### Backend

```bash
cd backend
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

#### Frontend

```bash
cd frontend
pnpm run build
pnpm run preview
```

### Windows (PowerShell)

Backend:
```powershell
cd backend
poetry run uvicorn app.main:app --reload --port 8000
```

Frontend:
```powershell
cd frontend
pnpm run dev
```

O servir con nginx/apache los archivos en `frontend/dist/`.

## Usando Scripts de Setup

### Linux/macOS

```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

### Windows (PowerShell)

```powershell
.\scripts\setup.ps1
```

## Usando Makefile

```bash
# Setup completo
make setup

# Ejecutar backend
make run-backend

# Ejecutar frontend
make run-frontend

# Ejecutar tests
make test-backend
make test-frontend

# Linting
make lint-backend
make lint-frontend
```

## Verificación

1. **Backend saludable:**
   ```bash
   curl http://localhost:8000/health
   ```

2. **API disponible:**
   ```bash
   curl http://localhost:8000/api/v1/recommendation/today
   ```

3. **Frontend accesible:**
   Abrir http://localhost:5173 en el navegador

## Solución de Problemas

### Error: Poetry no encontrado
```bash
export PATH="$HOME/.local/bin:$PATH"
```

### Error: pnpm no encontrado
```bash
npm install -g pnpm
```

### Error: Puerto 8000 en uso
Cambiar el puerto en el comando de uvicorn o en la configuración.

### Error: Dependencias Python faltantes
```bash
cd backend
poetry install --no-root
```

### Error: Dependencias Node faltantes
```bash
cd frontend
rm -rf node_modules pnpm-lock.yaml
pnpm install
```

## Próximos Pasos

1. Revisar [Metodología](methodology.md)
2. Consultar [Runbooks](runbooks/) para operación
3. Ver [Backtest Report](backtest-report.md) para resultados históricos

