# Runbook: Datos Incompletos

## Síntomas
- Gaps en datos históricos
- Métricas `ost_data_gaps_total` incrementando
- Señales no generadas por falta de datos
- Logs muestran "Insufficient data" o "No data in date range"

## Diagnóstico

### 1. Verificar gaps en datos
```bash
cd /opt/one-smart-trade/backend
python -c "
from app.data.curation import DataCuration
from datetime import datetime, timedelta
dc = DataCuration()
df = dc.get_latest_curated('1d')
if df.empty:
    print('No data available')
else:
    print(f'Data range: {df.iloc[0][\"open_time\"]} to {df.iloc[-1][\"open_time\"]}')
    print(f'Total rows: {len(df)}')
    # Check for gaps
    df['date'] = pd.to_datetime(df['open_time']).dt.date
    expected_days = (df['date'].max() - df['date'].min()).days
    actual_days = len(df['date'].unique())
    print(f'Expected days: {expected_days}, Actual: {actual_days}')
"
```

### 2. Verificar logs de ingesta
```bash
journalctl -u one-smart-trade-backend -n 500 --no-pager | grep -i "gap\|incomplete\|missing"
```

### 3. Verificar métricas
```bash
curl -s http://localhost:8000/metrics | grep ost_data_gaps_total
```

## Mitigación

### Paso 1: Backfill manual
```bash
cd /opt/one-smart-trade/backend
python -c "
import asyncio
from app.data.ingestion import DataIngestion
from datetime import datetime, timedelta

async def backfill():
    di = DataIngestion()
    # Backfill last 30 days
    end = datetime.utcnow()
    start = end - timedelta(days=30)
    for tf in ['15m', '30m', '1h', '4h', '1d', '1w']:
        print(f'Backfilling {tf}...')
        await di.ingest_timeframe(tf, start, end)

asyncio.run(backfill())
"
```

### Paso 2: Verificar datos raw
```bash
# Verificar archivos Parquet
ls -lh data/raw/*/
# Verificar tamaño y fechas de modificación
```

### Paso 3: Regenerar datos curados
```bash
python -c "
from app.data.curation import DataCuration
dc = DataCuration()
for tf in ['15m', '30m', '1h', '4h', '1d', '1w']:
    print(f'Curating {tf}...')
    dc.curate_timeframe(tf)
"
```

### Paso 4: Si gaps persisten
- Verificar conectividad a Binance
- Verificar espacio en disco
- Verificar permisos de escritura en `data/`
- Considerar usar datos históricos alternativos

## Criterios de Salida
- ✅ Datos completos para últimos 30 días
- ✅ No gaps detectados en validación
- ✅ Señales se generan correctamente
- ✅ Métricas `ost_data_gaps_total` estables

## Prevención
- Validación de gaps en pipeline de ingesta
- Backfill automático en detección de gaps
- Alertas cuando gaps > 24 horas
- Monitoreo de espacio en disco
