# Changelog - One Smart Trade

Todos los cambios notables en este proyecto serán documentados en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/),
y este proyecto adhiere a [Semantic Versioning](https://semver.org/lang/es/).

## [0.1.0] - 2024-01-XX

### Epic 7 - Observabilidad y Operación Manual

#### Añadido
- ✅ Métricas Prometheus completas:
  - `ost_ingestion_duration_seconds`: Duración de ingesta por timeframe
  - `ost_ingestion_failures_total`: Fallos de ingesta con razón
  - `ost_signal_generation_duration_seconds`: Duración de generación de señal
  - `ost_signal_generation_failures_total`: Fallos de generación con razón
  - `ost_last_ingestion_timestamp_seconds`: Timestamp de última ingesta exitosa
  - `ost_last_signal_timestamp_seconds`: Timestamp de última señal exitosa
  - `ost_data_gaps_total`: Gaps de datos detectados
- ✅ Logging JSON estructurado con `pythonjsonlogger`
- ✅ Scripts de alertas:
  - `scripts/alerts/webhook_alert.py`: Envío de alertas vía webhook (Slack/Discord)
  - `scripts/alerts/email_alert.py`: Envío de alertas vía email SMTP
  - `scripts/alerts/check_alerts.py`: Health checks automatizados
- ✅ Runbooks completos:
  - `docs/runbooks/binance_down.md`: Manejo de caídas de Binance API
  - `docs/runbooks/data_incomplete.md`: Manejo de datos incompletos
  - `docs/runbooks/calc_failure.md`: Manejo de fallos de cálculo
  - `docs/runbooks/metrics_degradation.md`: Manejo de degradación de métricas
- ✅ Guía de despliegue manual (`docs/deployment.md`):
  - Configuración systemd service y timers
  - Variables de entorno
  - Rotación de logs
  - Backup y restauración
  - Recuperación tras reinicio
  - Monitoreo recomendado

#### Cambiado
- Scheduler jobs ahora reportan métricas de latencia y fallos
- Logging mejorado con contexto estructurado

### Epic 6 - Backtesting, Reporting y Transparencia

#### Añadido
- ✅ Motor de backtesting con soporte para 5+ años de datos
- ✅ Métricas profesionales:
  - CAGR, Sharpe, Sortino, Max Drawdown
  - Win Rate, Profit Factor, Expectancy, Calmar
  - Rolling KPIs (mensuales y trimestrales)
- ✅ Gráficos generados con matplotlib:
  - Equity curve
  - Drawdown chart
  - Distribución de retornos
  - Comparación Strategy vs Buy & Hold
- ✅ Reporte Markdown generado automáticamente (`docs/backtest-report.md`)
- ✅ Endpoint `/api/v1/performance/summary` con esquemas Pydantic documentados
- ✅ Persistencia de resultados versionados en BD (`BacktestResultORM`)
- ✅ Pruebas de consistencia y reproducibilidad

#### Cambiado
- Metodología actualizada con limitaciones detalladas y plan de recalibración

**Modelo versión:** 0.1.0

### Epic 5 - Frontend Minimalista de Alto Valor

#### Añadido
- ✅ Hooks React Query para todos los endpoints
- ✅ Componente `PerformanceSummary` para métricas de backtesting
- ✅ Gráfico `PriceLevelsChart` mejorado con datos reales del endpoint market
- ✅ Disclaimers legales visibles en footer
- ✅ Enlaces a documentación (metodología, backtesting, API)
- ✅ Accesibilidad WCAG AA (roles ARIA, contraste, focus visible)
- ✅ Pruebas de componentes e integración

#### Cambiado
- Componentes rediseñados para usar datos reales de API
- Dark theme mejorado con variables CSS
- Documentación Lighthouse actualizada

### Epic 4 - API y Scheduler

#### Añadido
- ✅ APScheduler integrado con jobs programados:
  - Ingesta cada 15 minutos
  - Señal diaria a horario configurable (default 12:00 UTC)
- ✅ Base de datos SQLAlchemy + Alembic:
  - Modelos: `RecommendationORM`, `RunLogORM`
  - Migraciones iniciales
- ✅ Endpoints FastAPI completos:
  - `/api/v1/recommendation/today`
  - `/api/v1/recommendation/history?limit=N`
  - `/api/v1/diagnostics/last-run`
  - `/api/v1/market/{interval}`
  - `/api/v1/performance/summary`
- ✅ Middlewares:
  - `ExceptionHandlerMiddleware`: Manejo robusto de excepciones
  - `RateLimitMiddleware`: 300 req/min por IP
  - `RequestMetricsMiddleware`: Métricas Prometheus
- ✅ Pruebas end-to-end con mocks de Binance
- ✅ Documentación API completa (`docs/api.md`)

### Epic 3 - Motor Cuantitativo Profesional

#### Añadido
- ✅ Indicadores técnicos completos:
  - EMA/SMA, MACD, RSI, StochRSI, ATR, Bollinger, Keltner, VWAP, volatilidad
- ✅ Factores cross-timeframe:
  - Momentum alignment (1h vs 1d)
  - Divergencias MACD/RSI
  - Slopes de medias móviles
  - Regímenes de volatilidad
- ✅ Estrategias individuales:
  - Momentum-trend
  - Mean-reversion
  - Breakout
  - Volatilidad
- ✅ Motor de señales:
  - Consolidación de estrategias
  - Rango de entrada (soportes/resistencias/VWAP)
  - SL/TP dinámicos (multiplicadores ATR adaptados)
  - Confianza (Monte Carlo + histórico)
- ✅ Análisis textual profesional
- ✅ Pruebas unitarias e integrales

#### Cambiado
- Metodología documentada con supuestos, limitaciones y recalibración

### Epic 2 - Ingesta Binance Multi-timeframe

#### Añadido
- ✅ Cliente asíncrono Binance (`binance_client.py`):
  - Rate limiting (1200 req/min)
  - Exponential backoff
  - Metadatos (latency_ms, fetched_at)
- ✅ Pipeline de ingesta (`ingestion.py`):
  - Control de concurrencia con Semaphore
  - Validación de gaps
  - Backfill automático
- ✅ Persistencia Parquet (`storage.py`):
  - Datos raw por timeframe
  - Metadatos incluidos
- ✅ Curación de datos (`curation.py`):
  - VWAP, ATR, volatilidad realizada
  - Soportes y resistencias
  - Validación de consistencia temporal
- ✅ Pruebas con mocks de throttling y respuestas vacías

### Epic 1 - Fundamentos sin Docker

#### Añadido
- ✅ Estructura de monorepo (backend/, frontend/, shared/, docs/, scripts/)
- ✅ Backend:
  - FastAPI con endpoints básicos
  - Poetry para gestión de dependencias
  - Ruff, mypy, pytest para calidad de código
- ✅ Frontend:
  - React + Vite + TypeScript
  - PNPM para gestión de dependencias
  - ESLint, Prettier, Vitest
- ✅ CI/CD:
  - GitHub Actions con matrices Python 3.11/3.12 y Node 20
  - Caches para Poetry y PNPM
- ✅ Scripts de setup para Linux/macOS/Windows
- ✅ Makefile para comandos comunes
- ✅ Documentación inicial:
  - README.md
  - INSTALLATION.md
  - ARCHITECTURE.md
  - methodology.md (estructura inicial)

## [Unreleased]

### Próximas mejoras
- Validación out-of-sample para backtesting
- Soporte para múltiples pares de trading
- Dashboard de métricas en tiempo real (Grafana)
- Integración con exchanges adicionales
- Optimización de queries y índices de BD
- Tests de carga y performance

### Enlaces
- [Metodología](docs/methodology.md)
- [Reporte de Backtesting](docs/backtest-report.md)
- [API Documentation](docs/api.md)
- [Runbooks](docs/runbooks/)
- [Deployment Guide](docs/deployment.md)
