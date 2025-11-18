# Runbook: Generación de Señal Diaria

Runbook operativo para el pipeline diario de generación de señales.

## Objetivo

Este runbook describe los pasos para ejecutar, monitorear y troubleshootear el pipeline diario que genera la recomendación de trading a las 12:00 UTC.

## Pipeline Automático

El pipeline se ejecuta automáticamente a las **12:00 UTC** mediante el scheduler de FastAPI.

### Verificación Pre-Pipeline (11:45 UTC)

**Checklist 15 minutos antes**:

```bash
# 1. Verificar que el servicio está corriendo
curl http://localhost:8000/health

# 2. Verificar última ingesta de datos
cd backend
poetry run python -c "
from app.data.curation import DataCuration
curation = DataCuration()
df_1h = curation.load_curated('binance', 'BTCUSDT', '1h')
latest = df_1h.index[-1]
from datetime import datetime, timezone
age_minutes = (datetime.now(timezone.utc) - latest.to_pydatetime()).total_seconds() / 60
print(f'Latest 1h candle: {latest}, age: {age_minutes:.1f} minutes')
assert age_minutes < 30, 'Data is too old'
"

# 3. Verificar logs recientes
tail -n 50 backend/logs/app.log | grep -i "pipeline\|ingestion\|error"
```

**Si algún check falla**:
- Ver runbook específico: `data_incomplete.md`, `calc_failure.md`

## Ejecución Manual (Si es Necesario)

### Paso 1: Iniciar Servicio (Si no está corriendo)

```bash
cd backend
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Paso 2: Ejecutar Pipeline Manualmente

```bash
# Opción A: Via API (si allow_replay está habilitado)
curl -X POST "http://localhost:8000/api/v1/recommendation/today?allow_replay=true"

# Opción B: Via script Python
cd backend
poetry run python -c "
import asyncio
from app.services.recommendation_service import RecommendationService

async def generate():
    service = RecommendationService()
    result = await service.generate_recommendation()
    if result:
        print(f'✅ Signal generated: {result.get(\"signal\")}')
        print(f'   Confidence: {result.get(\"confidence\")}%')
        print(f'   Recommendation ID: {result.get(\"id\")}')
    else:
        print('❌ Generation failed')

asyncio.run(generate())
"
```

### Paso 3: Verificar Resultado

```bash
# Ver última recomendación
curl http://localhost:8000/api/v1/recommendation/today | jq '{
  signal: .signal,
  confidence: .confidence,
  entry: .entry_range.optimal,
  sl: .stop_loss_take_profit.stop_loss,
  tp: .stop_loss_take_profit.take_profit,
  execution_plan: .execution_plan != null
}'
```

## Monitoreo Post-Pipeline

### Verificar Logs (12:05 UTC)

```bash
# Buscar logs del pipeline
tail -n 100 backend/logs/app.log | grep -A 20 "Pipeline.*Signal generated"

# Verificar auditoría
tail -n 100 backend/logs/app.log | grep -i "preflight audit"

# Verificar errores
tail -n 100 backend/logs/app.log | grep -i "error\|failed\|exception"
```

### Verificar Base de Datos

```bash
cd backend
poetry run python -c "
from app.core.database import SessionLocal
from app.db.models import RecommendationORM
from sqlalchemy import desc
from datetime import datetime, timezone

db = SessionLocal()
try:
    latest = db.query(RecommendationORM).order_by(desc(RecommendationORM.created_at)).first()
    if latest:
        print(f'Latest recommendation:')
        print(f'  ID: {latest.id}')
        print(f'  Signal: {latest.signal}')
        print(f'  Created: {latest.created_at}')
        print(f'  Status: {latest.status}')
        print(f'  Has execution plan: {latest.snapshot_json and \"execution_plan\" in str(latest.snapshot_json)}')
    else:
        print('No recommendations found')
finally:
    db.close()
"
```

## Troubleshooting

### Problema: Pipeline no se ejecutó

**Síntomas**:
- No hay logs de "Pipeline {run_id}" a las 12:00 UTC
- No hay nueva recomendación en DB

**Diagnóstico**:
```bash
# Verificar scheduler
ps aux | grep uvicorn
curl http://localhost:8000/health

# Verificar logs de scheduler
tail -n 200 backend/logs/app.log | grep -i "scheduler\|job_daily_pipeline"
```

**Solución**:
1. Verificar que el servicio está corriendo
2. Verificar timezone del servidor (debe ser UTC)
3. Ejecutar manualmente (ver Paso 2 arriba)
4. Revisar configuración: `RECOMMENDATION_UPDATE_TIME=12:00`

### Problema: Pipeline falló con error

**Síntomas**:
- Logs muestran "Pipeline {run_id}: Signal generation failed"
- Error específico en logs

**Diagnóstico**:
```bash
# Ver error completo
tail -n 200 backend/logs/app.log | grep -A 30 "Signal generation failed"
```

**Errores comunes**:

1. **"Data is stale"**:
   - Ver runbook: `data_incomplete.md`
   - Verificar ingesta: `poetry run python -m app.data.ingestion`

2. **"Backtest execution failed"**:
   - Verificar datos suficientes (>= 90 días)
   - Revisar configuración: `BACKTEST_ENABLED=true`
   - Ver logs de backtest

3. **"Preflight audit failed"**:
   - Ejecutar auditoría manual: `poetry run python backend/app/scripts/preflight_audit.py --generate`
   - Revisar checks fallidos
   - Ver runbook: `metrics_degradation.md`

4. **"Capital validation required"**:
   - Configurar capital: `POST /api/v1/risk/sizing` con capital
   - O deshabilitar validación (no recomendado)

### Problema: Señal generada pero no publicada

**Síntomas**:
- Logs muestran "Signal generated" pero no hay recomendación en DB
- Status "audit_failed" en respuesta

**Diagnóstico**:
```bash
# Ver logs de auditoría
tail -n 100 backend/logs/app.log | grep -i "preflight audit"
```

**Solución**:
1. Ejecutar auditoría manual para ver checks fallidos
2. Corregir problema específico (datos, seed, backtest, KPIs, execution plan)
3. Re-ejecutar pipeline

### Problema: Execution plan faltante

**Síntomas**:
- Recomendación existe pero `execution_plan` es null
- Check "execution_plan_ready" falla

**Diagnóstico**:
```bash
# Verificar si execution plan se generó
curl http://localhost:8000/api/v1/recommendation/today | jq '.execution_plan'
```

**Solución**:
1. Verificar que `_build_execution_plan` se ejecutó
2. Verificar logs: "Building execution plan"
3. Si falta, regenerar recomendación con `allow_replay=true`

## Métricas de Éxito

### Pipeline Exitoso

- ✅ Log: "Pipeline {run_id}: Signal generated"
- ✅ Log: "Preflight audit PASSED"
- ✅ Recomendación en DB con status "closed" o "open"
- ✅ Execution plan presente en recomendación
- ✅ API responde con recomendación del día

### Tiempos Esperados

- **Ingesta**: < 5 segundos
- **Curación**: < 10 segundos
- **Generación de señal**: < 5 segundos
- **Backtest**: 30-60 segundos
- **Auditoría**: < 2 segundos
- **Total**: 50-80 segundos

### Alertas

**Si pipeline tarda > 2 minutos**:
- Revisar logs para identificar cuello de botella
- Verificar recursos del servidor (CPU, memoria)
- Considerar optimización

**Si pipeline falla 2 días consecutivos**:
- Escalar a equipo de desarrollo
- Revisar cambios recientes en código
- Verificar dependencias externas (Binance API)

## Checklist Post-Pipeline

- [ ] Pipeline ejecutado (verificar logs)
- [ ] Señal generada exitosamente
- [ ] Auditoría pasó todos los checks
- [ ] Recomendación guardada en DB
- [ ] Execution plan presente
- [ ] API responde correctamente
- [ ] No hay errores en logs
- [ ] Métricas registradas en Prometheus

## Escalación

**Si el problema no se resuelve**:

1. **Nivel 1**: Revisar este runbook y runbooks relacionados
2. **Nivel 2**: Consultar logs detallados y métricas
3. **Nivel 3**: Escalar a equipo de desarrollo con:
   - Logs completos del error
   - Output de diagnóstico
   - Timestamp del problema
   - Recomendación ID (si existe)

## Referencias

- **E2E Flow**: `docs/E2E_FLOW.md`
- **Paper Trading**: `docs/PAPER_TRADING_PLAYBOOK.md`
- **API Docs**: `docs/api.md`
- **Runbooks relacionados**: `data_incomplete.md`, `calc_failure.md`, `metrics_degradation.md`

