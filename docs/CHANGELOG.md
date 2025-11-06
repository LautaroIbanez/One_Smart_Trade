# Changelog - One Smart Trade

Todos los cambios notables en este proyecto serán documentados en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/),
y este proyecto adhiere a [Semantic Versioning](https://semver.org/lang/es/).

## [0.1.0] - 2024-01-XX

### Epic 1 - Fundamentos sin Docker

#### Añadido
- Estructura de monorepo (backend/, frontend/, docs/, scripts/)
- Configuración de backend con Poetry, FastAPI, SQLAlchemy
- Configuración de frontend con Vite, React, TypeScript
- Tooling: Ruff, mypy, pytest para backend
- Tooling: ESLint, Prettier, Vitest para frontend
- Scripts de setup para Linux/macOS/Windows
- Makefile para comandos comunes
- CI/CD con GitHub Actions (matrices Python 3.11/3.12 y Node 20)
- Documentación inicial:
  - README.md
  - INSTALLATION.md
  - ARCHITECTURE.md
  - methodology.md (estructura inicial)
- Endpoints básicos de API:
  - GET /api/v1/recommendation/today
  - GET /api/v1/recommendation/history
  - GET /api/v1/diagnostics/last-run
  - GET /api/v1/market/{interval}
  - GET /api/v1/performance/summary
- Componentes básicos de frontend:
  - Dashboard
  - RecommendationCard
  - HistoryTable
  - IndicatorsPanel
- Modelos de datos básicos (Pydantic)
- Tests básicos para backend y frontend

#### Pendiente (Próximos Epics)
- Epic 2: Ingesta Binance multi-timeframe
- Epic 3: Motor cuantitativo completo
- Epic 4: Scheduler y persistencia
- Epic 5: Frontend completo con visualizaciones
- Epic 6: Backtesting y reportes
- Epic 7: Observabilidad y runbooks
## [0.2.0] - 2025-11-06

### Epic 2 - Ingesta Binance Multi-timeframe
- Cliente asíncrono (httpx) con rate limiting y backoff
- Persistencia Parquet con metadatos (latencia, fetched_at)
- Curated datasets y validación temporal

### Epic 3 - Motor Cuantitativo Profesional
- Indicadores avanzados y factores cross-timeframe
- Estrategias (momentum, mean-reversion, breakout, volatilidad) y consolidación
- SL/TP dinámicos y confianza Monte Carlo

### Epic 4 - API y Scheduler
- APScheduler para ingesta y señal diaria
- Persistencia en SQLite (ORM SQLAlchemy)
- Endpoints recommendation/history/diagnostics/market/performance
- Rate limiting y logging JSON

### Epic 5 - Frontend Minimalista de Alto Valor
- Hooks React Query, gráficos y paneles de riesgo/indicadores
- Disclaimers y accesibilidad

### Epic 6 - Backtesting, Reporting y Transparencia
- Motor de backtesting con comisiones/slippage
- Métricas profesionales y reportes con gráficos

### Epic 7 - Observabilidad y Operación Manual
- Métricas Prometheus en `/metrics`
- Scripts de alertas (webhook/email)
- Runbooks por incidente y guía de despliegue manual

### Notas
- Versión inicial del proyecto
- Estructura base lista para desarrollo
- Todas las funcionalidades core están pendientes de implementación

