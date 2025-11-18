# Flujo End-to-End: Generación de Señales Diarias

Este documento describe el flujo completo del sistema desde la ingesta de datos hasta la publicación de recomendaciones diarias.

## Visión General

El sistema genera una recomendación diaria de trading (BUY/SELL/HOLD) a las 12:00 UTC mediante un pipeline determinista y reproducible que incluye:

1. **Ingesta de datos** (cada 15 minutos)
2. **Curación de datos** (validación y enriquecimiento)
3. **Generación de señal** (12:00 UTC diario)
4. **Validación y auditoría** (preflight checks)
5. **Publicación** (API y base de datos)

## Arquitectura del Pipeline

```
┌─────────────────┐
│  Data Ingestion │  (Cada 15 min)
│  - Binance API  │
│  - OHLCV 1h/1d  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Data Curation   │  (Validación, indicadores)
│ - Gaps check    │
│ - Indicators    │
│ - Factors       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Signal Engine   │  (12:00 UTC diario)
│ - Strategies    │
│ - Aggregation   │
│ - Confidence    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ SL/TP Policy    │
│ - ATR-based     │
│ - Support/Res   │
│ - RR validation │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Backtest        │  (Mandatory)
│ - 90 days       │
│ - Realistic exec│
│ - Metrics       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Preflight Audit │  (5 checks)
│ - Data fresh    │
│ - Seed fixed    │
│ - Backtest OK   │
│ - KPIs > thresh │
│ - Exec plan     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Publication     │
│ - DB save       │
│ - API response  │
│ - Execution plan│
└─────────────────┘
```

## Componentes Principales

### 1. Data Ingestion (`app.data.ingestion`)

**Frecuencia**: Cada 15 minutos  
**Fuente**: Binance API  
**Datos**: OHLCV para timeframes 1h y 1d

**Configuración**:
- Intervalos: `1h`, `1d`
- Símbolo: `BTCUSDT`
- Venue: `binance`

**Almacenamiento**:
- Raw data: `backend/data/raw/binance/BTCUSDT/{interval}/klines.parquet`
- Formato: Parquet con partición por fecha

### 2. Data Curation (`app.data.curation`)

**Propósito**: Validar y enriquecer datos con indicadores técnicos

**Validaciones**:
- Gaps en datos (máximo 2 velas faltantes)
- Freshness (máximo 90 minutos de antigüedad)
- Completitud de columnas OHLCV

**Indicadores calculados**:
- RSI, MACD, ATR, Bollinger Bands
- Volatilidad realizada
- Support/Resistance levels
- Cross-timeframe factors

**Almacenamiento**:
- Curated data: `backend/data/curated/binance/BTCUSDT/{interval}/latest.parquet`

### 3. Signal Engine (`app.quant.signal_engine`)

**Motor unificado** que combina múltiples estrategias:

**Estrategias incluidas**:
- Momentum (breakout, trend following)
- Mean reversion (RSI, Bollinger)
- Volatility-based (ATR, regime detection)
- Cross-timeframe alignment

**Proceso**:
1. Calcula indicadores en 1h y 1d
2. Ejecuta cada estrategia independientemente
3. Agrega votos (BUY/SELL/HOLD)
4. Calcula confianza con Monte Carlo
5. Aplica guardrails (RR ratio, risk limits)

**Determinismo**:
- Seed basada en fecha + símbolo
- Mismo día + mismo símbolo = misma señal
- Reproducible 100%

### 4. SL/TP Policy (`app.services.strategy_service`)

**Ajuste de niveles** basado en:
- ATR (Average True Range)
- Support/Resistance levels
- Risk/Reward mínimo (1.2x por defecto)

**Validaciones**:
- SL no puede estar por debajo de support (BUY)
- TP debe cumplir RR mínimo
- Niveles deben ser alcanzables (orderbook validation)

### 5. Backtest Mandatory (`app.backtesting.engine`)

**Ejecución obligatoria** antes de publicar:

**Configuración**:
- Lookback: 90 días
- Capital inicial: $10,000
- Commission: 0.1%
- Slippage: 5 bps

**Métricas calculadas**:
- CAGR (Compound Annual Growth Rate)
- Win rate
- Risk/Reward ratio
- Max drawdown
- Sharpe ratio

**Validación**:
- Sharpe >= 0.0 (no negativo)
- Max drawdown <= 50%
- Backtest debe completarse sin errores

### 6. Preflight Audit (`app.services.preflight_audit_service`)

**5 checks obligatorios**:

1. **Data Freshness**: Datos < 90 minutos
2. **Seed Fixed**: Seed presente y válida
3. **Backtest OK**: Backtest ejecutado y métricas OK
4. **KPIs > Threshold**: Confianza >= 30%, RR >= 1.2
5. **Execution Plan Ready**: Plan de ejecución completo

**Bloqueo**: Si cualquier check falla, la recomendación NO se publica.

### 7. Execution Plan (`app.services.recommendation_service._build_execution_plan`)

**Playbook manual** incluido en cada recomendación:

- **Ventana operativa**: Óptima 4h, aceptable 24h
- **Tipo de orden**: Limit o Market (según precio actual)
- **Tamaño sugerido**: Basado en capital mínimo o personalizado
- **Instrucciones paso a paso**: En español
- **Notas y advertencias**: Drawdown, sizing, etc.

## Flujo Temporal

### Pipeline Diario (12:00 UTC)

```
11:45 UTC - Última ingesta de datos (15 min antes)
12:00 UTC - Pipeline diario inicia
  ├─ 12:00:00 - Data validation
  ├─ 12:00:05 - Signal generation
  ├─ 12:00:10 - SL/TP policy application
  ├─ 12:00:15 - Backtest execution (~30-60s)
  ├─ 12:00:45 - Preflight audit
  └─ 12:00:50 - Publication (si todos los checks pasan)
```

**Duración total**: ~50-60 segundos

### Ingesta Continua (Cada 15 minutos)

```
00:00, 00:15, 00:30, 00:45, 01:00, ... (cada 15 min)
  └─ Fetch latest candles from Binance
  └─ Save to raw data
  └─ Trigger curation (si hay nuevos datos)
```

## Dependencias

### Software

- **Python 3.11+**
- **Poetry** (gestión de dependencias)
- **SQLite** (base de datos)
- **FastAPI** (API server)
- **APScheduler** (scheduled jobs)

### Datos

- **Binance API** (acceso público, sin API key requerida)
- **Orderbook snapshots** (opcional, para validación SL/TP)

### Configuración

**Archivos principales**:
- `backend/app/core/config.py`: Configuración general
- `backend/app/quant/params.yaml`: Parámetros de estrategias
- `backend/config/performance.yaml`: Umbrales de performance

**Variables de entorno** (`.env`):
```bash
DATABASE_URL=sqlite:///./data/trading.db
LOG_LEVEL=INFO
RECOMMENDATION_UPDATE_TIME=12:00
DATA_FRESHNESS_THRESHOLD_MINUTES=90
BACKTEST_ENABLED=true
BACKTEST_LOOKBACK_DAYS=90
```

## Reproducción Manual

### Paso 1: Verificar Datos

```bash
cd backend
poetry run python -c "
from app.data.curation import DataCuration
curation = DataCuration()
df_1h = curation.load_curated('binance', 'BTCUSDT', '1h')
df_1d = curation.load_curated('binance', 'BTCUSDT', '1d')
print(f'1h data: {len(df_1h)} rows, latest: {df_1h.index[-1]}')
print(f'1d data: {len(df_1d)} rows, latest: {df_1d.index[-1]}')
"
```

### Paso 2: Generar Señal

```bash
poetry run python -c "
import asyncio
from app.services.recommendation_service import RecommendationService

async def generate():
    service = RecommendationService()
    result = await service.generate_recommendation()
    if result:
        print(f\"Signal: {result.get('signal')}\")
        print(f\"Confidence: {result.get('confidence')}%\")
        print(f\"Entry: {result.get('entry_range', {}).get('optimal')}\")
    else:
        print('Generation failed')

asyncio.run(generate())
"
```

### Paso 3: Verificar Auditoría

```bash
poetry run python backend/app/scripts/preflight_audit.py --generate
```

### Paso 4: Consultar Recomendación

```bash
# Via API
curl http://localhost:8000/api/v1/recommendation/today

# O directamente desde Python
poetry run python -c "
import asyncio
from app.services.recommendation_service import RecommendationService

async def get_today():
    service = RecommendationService()
    result = await service.get_today_recommendation(allow_replay=True)
    if result:
        print(f\"Signal: {result.get('signal')}\")
        print(f\"Execution plan: {result.get('execution_plan') is not None}\")
    else:
        print('No recommendation found')

asyncio.run(get_today())
"
```

## Troubleshooting

### Problema: "Data is stale"

**Causa**: Última vela > 90 minutos  
**Solución**: 
1. Verificar ingesta: `poetry run python -m app.data.ingestion`
2. Verificar conectividad con Binance
3. Revisar logs: `backend/logs/app.log`

### Problema: "Backtest failed"

**Causa**: Error en ejecución de backtest  
**Solución**:
1. Verificar datos suficientes (>= 90 días)
2. Revisar logs de backtest
3. Verificar configuración: `BACKTEST_ENABLED=true`

### Problema: "Preflight audit failed"

**Causa**: Algún check falló  
**Solución**:
1. Ejecutar auditoría manual: `poetry run python backend/app/scripts/preflight_audit.py`
2. Revisar checks fallidos en el output
3. Corregir el problema específico (datos, seed, backtest, KPIs, execution plan)

### Problema: "No recommendation available"

**Causa**: Pipeline no se ejecutó o falló  
**Solución**:
1. Verificar scheduler: logs de `job_daily_pipeline`
2. Ejecutar manualmente con `allow_replay=True`
3. Revisar errores en logs

## Monitoreo

### Logs

**Ubicación**: `backend/logs/app.log`

**Eventos importantes**:
- `Pipeline {run_id}: Signal generated` - Señal generada exitosamente
- `Preflight audit PASSED` - Auditoría exitosa
- `Preflight audit FAILED` - Auditoría falló (bloquea publicación)

### Métricas Prometheus

**Endpoints**:
- `/metrics`: Métricas Prometheus
- `/api/v1/observability/metrics`: Métricas detalladas

**Métricas clave**:
- `signal_generation_duration_seconds`: Duración de generación
- `signal_generation_success_total`: Señales generadas exitosamente
- `preflight_audit_checks_total`: Checks de auditoría ejecutados

### Base de Datos

**Tabla**: `recommendations`

**Consultas útiles**:
```sql
-- Última recomendación
SELECT * FROM recommendations ORDER BY created_at DESC LIMIT 1;

-- Recomendaciones del día
SELECT * FROM recommendations WHERE date = date('now');

-- Recomendaciones con auditoría fallida (si se guardan)
SELECT * FROM recommendations WHERE status = 'audit_failed';
```

## Próximos Pasos

1. **Paper Trading**: Ver `docs/PAPER_TRADING_PLAYBOOK.md`
2. **Configuración Avanzada**: Ver `docs/INSTALLATION.md`
3. **Troubleshooting**: Ver `docs/runbooks/`
4. **API Reference**: Ver `docs/api.md`

