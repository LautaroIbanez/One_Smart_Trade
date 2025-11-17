# Data Pipeline - One Smart Trade

## Objetivo
Ingestar datos de BTCUSDT desde la API pública de Binance en múltiples timeframes, persistir crudos en Parquet con metadatos, curar datasets diarios y alimentar el motor cuantitativo, con control de cuotas y resiliencia.

## Arquitectura
```
Binance API → BinanceClient (httpx, backoff, rate limit)
           → Ingestion (batching, colas por timeframe, gaps)
           → Storage RAW (Parquet data/raw/<interval>/)
           → Curation Básica (casting, dropna, dedupe)
           → DataQualityPipeline (sanitización estadística)
           → CrossVenueReconciler (reconciliación multi-venue)
           → Indicadores Técnicos (VWAP/ATR/vol/RSI/etc)
           → Curated (Parquet data/curated/) con quality_pass=True
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
  - Curación básica: casting numérico, dropna, deduplicación.
  - **DataQualityPipeline**: Limpieza estadística avanzada:
    - Detección de outliers por z-score (retornos > 6σ)
    - Detección de outliers por MAD (volumen)
    - Winsorización (0.5% / 99.5%)
    - Interpolación temporal
  - **CrossVenueReconciler**: Reconciliación multi-venue:
    - Comparación de precios entre venues
    - Tolerancia configurable (default: 5 bps)
    - Flagging de discrepancias
    - Abort si tasa de discrepancia > umbral (default: 3%)
  - Cálculo de indicadores técnicos: `vwap`, `atr`, `realized_volatility`, `returns`, `key levels` (support/resistance/pivot), consistencia temporal y orden cronológico.
  - Persistencia de reportes de discrepancias en `data/audits/`

## Cronograma de Actualizaciones
- Ingesta:
  - 15m/30m: cada 15 minutos
  - 1h: cada hora
  - 4h/1d/1w: en su cierre o junto a job de 15 min (configurable)
- Señal diaria: `RECOMMENDATION_UPDATE_TIME` (por defecto 12:00 UTC)

## Requisitos de Almacenamiento
- Formato columnar Parquet con compresión `snappy`.
- Metadata incluye flags: `quality_applied`, `reconciler_applied`, `quality_pass`, `quality_stats`, `discrepancies`.

## Pipeline de Calidad de Datos

### DataQualityPipeline

Aplica limpieza estadística avanzada:

1. **Detección de outliers por retornos**:
   - Calcula z-scores de log returns
   - Marca como NaN valores con |z| > 6.0 (configurable)

2. **Detección de outliers por volumen**:
   - Usa Median Absolute Deviation (MAD)
   - Marca como NaN volúmenes con desviación > 10× MAD (configurable)

3. **Winsorización**:
   - Limita valores extremos a percentiles 0.5% / 99.5% (configurable)

4. **Interpolación**:
   - Interpola valores faltantes usando método temporal
   - Límite: 2 períodos consecutivos (configurable)

### CrossVenueReconciler

Valida consistencia entre múltiples venues:

1. **Alineación temporal**: Alinea timestamps de diferentes venues
2. **Comparación de precios**: Calcula diferencias en bps
3. **Detección de discrepancias**: Flaggea diferencias > tolerancia (default: 5 bps)
4. **Validación de tasa**: Aborta si tasa de discrepancia > umbral (default: 3%)

### Gestión de Discrepancias

- **Reportes persistidos**: `data/audits/<venue>/<symbol>/discrepancies_<interval>_<timestamp>.json`
- **Flags en dataset**: Columna `reconciled_flag` marca filas con discrepancias
- **Abort automático**: `DataIntegrityError` si tasa > umbral

## Checklist Operativo

Antes de usar datos curados en backtests:

- [ ] Revisar reporte de discrepancias diario en `data/audits/`
- [ ] Confirmar `quality_pass = True` en metadata del dataset
- [ ] Verificar `quality_stats` muestra saneamiento razonable
- [ ] Si hay discrepancias, revisar `discrepancies` en metadata
- [ ] Confirmar `reconciled_flag` no tiene falsos en períodos críticos

## Política de Datos

**Ningún dataset pasa a backtests sin `quality_pass = True`**

- Todos los datasets curados deben tener `quality_applied = True`
- En modo multi-venue, `reconciler_applied = True` es obligatorio
- Tasa de discrepancia > 3% aborta la curación automáticamente
- Particiones por `interval` y fecha (YYYYMMDD) para facilitar housekeeping.
- Directorios configurables: `RAW_DATA_DIR`, `CURATED_DATA_DIR`.

## Operación y Backfill Manual
```bash
# Ingesta de 1h últimos 7 días
cd backend
python -c "
import asyncio
from datetime import datetime, timedelta
from app.data.ingestion import DataIngestion

di = DataIngestion()
end = datetime.utcnow()
start = end - timedelta(days=7)
result = asyncio.run(di.ingest_timeframe('1h', start, end))
print(result)
"

# Curación de 1h
python -c "
from app.data.curation import DataCuration
dc = DataCuration()
result = dc.curate_timeframe('1h')
print(f'Curated: {result}')
"
```

## Observabilidad
- Latencia y conteo de peticiones: Prometheus `/metrics` (ver `app/observability/metrics.py`).
- Logs JSON con nivel configurable `LOG_LEVEL`.

## Pruebas
- `backend/tests/data/test_ingestion_pipeline.py`: mocks de Binance (throttling, respuestas vacías) y verificación de integridad temporal.

## Limitaciones
- Dependencia de disponibilidad de Binance.
- Backfill intensivo puede alcanzar límites; usar batch y pausas.

