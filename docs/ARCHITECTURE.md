# Arquitectura - One Smart Trade

## Visión General

One Smart Trade sigue una arquitectura de monorepo con separación clara entre backend (Python/FastAPI) y frontend (React/Vite).

## Estructura del Proyecto

```
One Smart Trade/
├── backend/                 # Backend Python
│   ├── app/
│   │   ├── api/            # Endpoints FastAPI
│   │   ├── core/           # Configuración y utilidades
│   │   ├── models/         # Modelos de datos
│   │   ├── services/       # Lógica de negocio
│   │   ├── data/           # Ingesta y procesamiento
│   │   ├── indicators/     # Cálculo de indicadores
│   │   ├── strategies/     # Estrategias de trading
│   │   └── backtesting/    # Motor de backtesting
│   ├── tests/              # Tests automatizados
│   └── data/               # Datos persistentes
├── frontend/               # Frontend React
│   ├── src/
│   │   ├── components/     # Componentes React
│   │   ├── pages/          # Páginas
│   │   ├── services/       # Clientes API
│   │   └── test/           # Tests
│   └── public/             # Assets estáticos
├── shared/                 # Código compartido (futuro)
├── docs/                   # Documentación
├── scripts/                # Scripts de utilidad
└── .github/                # CI/CD
```

## Backend

### Stack Tecnológico

- **Framework:** FastAPI
- **Base de Datos:** SQLite (desarrollo) / PostgreSQL (producción)
- **ORM:** SQLAlchemy
- **Scheduler:** APScheduler
- **Análisis:** Pandas, NumPy, SciPy
- **Indicadores:** TA-Lib
- **Persistencia:** Parquet (PyArrow)

### Componentes Principales

#### 1. API Layer (`app/api/`)

- **v1/recommendation:** Endpoints de recomendaciones
- **v1/diagnostics:** Diagnósticos del sistema
- **v1/market:** Datos de mercado
- **v1/performance:** Métricas de performance

#### 2. Services Layer (`app/services/`)

- **RecommendationService:** Gestión de recomendaciones
- **MarketService:** Operaciones de mercado
- **DiagnosticsService:** Diagnósticos
- **PerformanceService:** Métricas de backtesting

#### 3. Data Layer (`app/data/`)

- **BinanceClient:** Cliente para API de Binance
- **DataIngestion:** Pipeline de ingesta
- **DataStorage:** Persistencia de datos

#### 4. Indicators (`app/indicators/`)

- Cálculo de indicadores técnicos
- Agregación multi-timeframe

#### 5. Strategies (`app/strategies/`)

- Implementación de estrategias
- Sistema de votación/consolidación

#### 6. Backtesting (`app/backtesting/`)

- Motor de backtesting
- Cálculo de métricas

### Flujo de Datos

```
Binance API → Data Ingestion → Raw Storage (Parquet)
                                    ↓
                            Data Curation
                                    ↓
                            Indicators Calculation
                                    ↓
                            Strategy Execution
                                    ↓
                            Signal Consolidation
                                    ↓
                            Risk Management
                                    ↓
                            Recommendation Generation
                                    ↓
                            Database Storage
                                    ↓
                            API Exposure
```

## Frontend

### Stack Tecnológico

- **Framework:** React 18
- **Build Tool:** Vite
- **State Management:** React Query
- **HTTP Client:** Axios
- **Charts:** Recharts
- **Styling:** CSS Modules

### Componentes Principales

#### 1. Pages (`src/pages/`)

- **Dashboard:** Vista principal con recomendación actual

#### 2. Components (`src/components/`)

- **RecommendationCard:** Tarjeta de recomendación principal
- **HistoryTable:** Tabla de historial
- **IndicatorsPanel:** Panel de indicadores

#### 3. Services (`src/services/`)

- **api.ts:** Cliente API

### Flujo de UI

```
Dashboard
    ├── RecommendationCard (señal actual)
    ├── IndicatorsPanel (indicadores clave)
    └── HistoryTable (historial reciente)
```

## Scheduler

El scheduler (APScheduler) ejecuta:

1. **Ingesta de Datos:** Según frecuencia de cada timeframe
2. **Cálculo de Indicadores:** Después de cada ingesta
3. **Generación de Recomendación:** Diariamente a las 12:00 UTC
4. **Backtesting:** Semanalmente

## Base de Datos

### Esquema Principal

- **recommendations:** Recomendaciones diarias
- **market_data:** Datos de mercado agregados
- **backtest_results:** Resultados de backtesting
- **system_logs:** Logs del sistema

## Seguridad

- Sin autenticación (requisito)
- Rate limiting básico en API
- Validación de inputs con Pydantic
- CORS configurado para frontend

## Observabilidad

- Logging estructurado (JSON)
- Métricas Prometheus-compatible
- Health checks
- Endpoints de diagnóstico

## Escalabilidad

- Backend stateless (horizontal scaling posible)
- Base de datos puede migrarse a PostgreSQL
- Frontend estático (CDN-friendly)
- Caching de recomendaciones en memoria

## Deployment

### Desarrollo

- Backend: `uvicorn` con auto-reload
- Frontend: `vite dev server`

### Producción

- Backend: `uvicorn` con múltiples workers
- Frontend: Build estático servido por nginx/apache
- Scheduler: Ejecutado en proceso principal

## Próximas Mejoras

- Migración a PostgreSQL para producción
- Caching con Redis
- WebSockets para actualizaciones en tiempo real
- Tests de integración E2E

