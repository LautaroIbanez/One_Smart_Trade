# Runbook: Fallo de Cálculo de Señal

## Síntomas
- Señal no generada en horario esperado
- Métricas `ost_signal_generation_failures_total` incrementando
- Logs muestran excepciones en `signal_engine.py` o `strategies.py`
- Endpoint `/api/v1/recommendation/today` retorna 404

## Diagnóstico

### 1. Verificar último run de señal
```bash
cd /opt/one-smart-trade/backend
python -c "
from app.core.database import SessionLocal
from app.db.crud import get_last_run
with SessionLocal() as db:
    run = get_last_run(db, 'signal')
    if run:
        print(f'Status: {run.status}')
        print(f'Time: {run.finished_at}')
        print(f'Message: {run.message}')
    else:
        print('No signal runs found')
"
```

### 2. Verificar datos curados disponibles
```bash
python -c "
from app.data.curation import DataCuration
dc = DataCuration()
df_1d = dc.get_latest_curated('1d')
df_1h = dc.get_latest_curated('1h')
print(f'1d data: {len(df_1d)} rows, latest: {df_1d.iloc[-1][\"open_time\"] if not df_1d.empty else \"None\"}')
print(f'1h data: {len(df_1h)} rows, latest: {df_1h.iloc[-1][\"open_time\"] if not df_1h.empty else \"None\"}')
"
```

### 3. Revisar logs de errores
```bash
journalctl -u one-smart-trade-backend -n 500 --no-pager | grep -i "signal\|calculation\|error"
```

### 4. Probar generación manual
```bash
python -c "
from app.data.curation import DataCuration
from app.quant.signal_engine import generate_signal
dc = DataCuration()
df_1d = dc.get_latest_curated('1d')
df_1h = dc.get_latest_curated('1h')
try:
    signal = generate_signal(df_1h, df_1d)
    print(f'Signal generated: {signal[\"signal\"]}')
except Exception as e:
    print(f'Error: {type(e).__name__}: {e}')
    import traceback
    traceback.print_exc()
"
```

## Mitigación

### Paso 1: Verificar datos
Si datos faltan, seguir runbook de "Datos Incompletos"

### Paso 2: Regenerar señal manualmente
```bash
cd /opt/one-smart-trade/backend
python -c "
import asyncio
from app.main import job_generate_signal
asyncio.run(job_generate_signal())
"
```

### Paso 3: Si error persiste
- Verificar versión de dependencias: `poetry show`
- Verificar memoria disponible: `free -h`
- Verificar logs completos para stack trace
- Considerar rollback a versión anterior si error es nuevo

### Paso 4: Workaround temporal
Si cálculo falla pero datos están disponibles, usar señal anterior:
```bash
python -c "
from app.core.database import SessionLocal
from app.db.crud import get_latest_recommendation
with SessionLocal() as db:
    rec = get_latest_recommendation(db)
    if rec:
        print(f'Last signal: {rec.signal} from {rec.created_at}')
"
```

## Criterios de Salida
- ✅ Señal generada exitosamente
- ✅ Endpoint `/api/v1/recommendation/today` retorna 200
- ✅ Logs no muestran errores
- ✅ Métricas `ost_signal_generation_failures_total` no incrementan

## Escalación
- **Primera falla:** Reintentar manualmente
- **Fallas repetidas:** Revisar logs, verificar datos
- **Fallas persistentes:** Escalar a desarrollo, considerar rollback

## Prevención
- Validación de datos antes de cálculo
- Manejo robusto de excepciones
- Logging detallado de errores
- Tests automatizados de cálculo
