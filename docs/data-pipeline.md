# Data Pipeline - One Smart Trade

## Objetivo
Ingestar datos de BTCUSDT desde la API pública de Binance en múltiples timeframes, persistir crudos en Parquet con metadatos, curar datasets diarios y alimentar el motor cuantitativo, con control de cuotas y resiliencia.

## Arquitectura
```
Binance API → BinanceClient (httpx, backoff, rate limit)
           → Ingestion (batching, colas por timeframe, gaps)
           → Storage RAW (Parquet data/raw/<interval>/)
           → Curation (agregados diarios, VWAP/ATR/vol)
           → Curated (Parquet data/curated/)
```

## Componentes
- `app/data/binance_client.py`: Cliente asíncrono httpx.
  - Endpoints: `klines`, `ticker/price`, `ticker/24hr`, `ping`.
  - Rate limiting: ventana configurable (`BINANCE_RATE_LIMIT_*`), semáforo de concurrencia.
  - Backoff exponencial y manejo de `429` (Retry-After).
  - Metadatos: `latency_ms`, `fetched_at`, `endpoint`.
- `app/data/ingestion.py`: Pipeline de ingesta.
  - Timeframes soportados: 15m, 30m, 1h, 4h, 1d, 1w.
  - Batching por `limit` y partición temporal; colas por intervalo con `asyncio.Semaphore`.
  - Validación de gaps (`check_gaps`) y backfill.
  - Logging estructurado por intervalo, latencia y estatus.
- `app/data/storage.py`: Persistencia Parquet.
  - RAW: `data/raw/<interval>/<SYMBOL>_<interval>_<YYYYMMDD>.parquet` con metadatos (fuente, latencia, fetched_at, interval, symbol).
  - Curated: `data/curated/<interval>_curated_<YYYYMMDD>.parquet`.
- `app/data/curation.py`: Curación y agregados.
  - Cálculo de `vwap`, `atr`, `realized_volatility`, `returns`, `key levels` (support/resistance/pivot), consistencia temporal y orden cronológico.

## Cronograma de Actualizaciones
- Ingesta:
  - 15m/30m: cada 15 minutos
  - 1h: cada hora
  - 4h/1d/1w: en su cierre o junto a job de 15 min (configurable)
- Señal diaria: `RECOMMENDATION_UPDATE_TIME` (por defecto 12:00 UTC)

## Requisitos de Almacenamiento
- Formato columnar Parquet con compresión `snappy`.
- Particiones por `interval` y fecha (YYYYMMDD) para facilitar housekeeping.
- Directorios configurables: `RAW_DATA_DIR`, `CURATED_DATA_DIR`.

## Operación y Backfill Manual
```bash
# Ingesta de 1h últimos 7 días
python - << 'PY'
import asyncio
from datetime import datetime, timedelta
from app.data.ingestion import DataIngestion

di = DataIngestion()
asyncio.run(di.ingest_timeframe('1h', datetime.utcnow()-timedelta(days=7), datetime.utcnow()))
PY

# Curación de 1h
python - << 'PY'
from app.data.curation import DataCuration
print(DataCuration().curate_timeframe('1h'))
PY
```

## Observabilidad
- Latencia y conteo de peticiones: Prometheus `/metrics` (ver `app/observability/metrics.py`).
- Logs JSON con nivel configurable `LOG_LEVEL`.

## Pruebas
- `backend/tests/data/test_ingestion_pipeline.py`: mocks de Binance (throttling, respuestas vacías) y verificación de integridad temporal.

## Limitaciones
- Dependencia de disponibilidad de Binance.
- Backfill intensivo puede alcanzar límites; usar batch y pausas.

