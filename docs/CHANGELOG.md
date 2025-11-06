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

### Notas
- Versión inicial del proyecto
- Estructura base lista para desarrollo
- Todas las funcionalidades core están pendientes de implementación

