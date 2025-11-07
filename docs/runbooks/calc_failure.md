# Runbook: Fallo de Cálculo de Señal

## Síntomas
- Señal no generada en horario esperado
- Métricas `signal_generation_failure_total` incrementando
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
cd /opt/one-smart-trade/backend
# Verificar gaps en datos (indica si hay datos disponibles)
poetry run python -m app.scripts.check_gaps --interval 1d --days 7
poetry run python -m app.scripts.check_gaps --interval 1h --days 7
```

### 3. Revisar logs de errores
```bash
journalctl -u one-smart-trade-backend -n 500 --no-pager | grep -i "signal\|calculation\|error"
```

### 4. Probar generación manual
```bash
cd /opt/one-smart-trade/backend
# Regenerar señal manualmente
poetry run python -m app.scripts.regenerate_signal
```

## Mitigación

### Paso 1: Verificar datos
Si datos faltan, seguir runbook de "Datos Incompletos"

### Paso 2: Regenerar señal manualmente
```bash
cd /opt/one-smart-trade/backend
poetry run python -m app.scripts.regenerate_signal
```

### Paso 3: Si faltan datos, regenerar
```bash
# Backfill si es necesario
poetry run python -m app.scripts.backfill --interval 1d --since 2024-01-01
poetry run python -m app.scripts.backfill --interval 1h --since 2024-01-01

# Curar datos (se hace automáticamente en backfill, pero se puede hacer manualmente)
poetry run python -m app.scripts.curate --interval 1d
poetry run python -m app.scripts.curate --interval 1h
```

### Paso 4: Si error persiste
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
- ✅ Métricas `signal_generation_failure_total` no incrementan

## Escalación
- **Primera falla:** Reintentar manualmente
- **Fallas repetidas:** Revisar logs, verificar datos
- **Fallas persistentes:** Escalar a desarrollo, considerar rollback

## Prevención
- Validación de datos antes de cálculo
- Manejo robusto de excepciones
- Logging detallado de errores
- Tests automatizados de cálculo
