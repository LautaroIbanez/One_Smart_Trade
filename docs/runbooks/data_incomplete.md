# Runbook: Datos incompletos

## Síntomas
- Gaps en series temporales
- Indicadores inconsistentes

## Diagnóstico
```bash
python - << 'PY'
from app.data.ingestion import DataIngestion
from datetime import datetime, timedelta

di = DataIngestion()
print(di.check_gaps('1h', datetime.utcnow()-timedelta(days=7), datetime.utcnow()))
PY
```

## Mitigación
1. Ejecutar backfill del timeframe afectado:
```bash
python - << 'PY'
import asyncio
from app.data.ingestion import DataIngestion
from datetime import datetime, timedelta

di = DataIngestion()
asyncio.run(di.ingest_timeframe('1h', datetime.utcnow()-timedelta(days=7), datetime.utcnow()))
PY
```
2. Re-generar curated:
```bash
python - << 'PY'
from app.data.curation import DataCuration
DataCuration().curate_timeframe('1h')
PY
```

## Prevención
- Validación de gaps en pipeline
- Alertas si gap > 2× intervalo

