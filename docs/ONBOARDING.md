# Onboarding Rápido - One Smart Trade

Guía de onboarding para nuevos operadores. Objetivo: operar el sistema en ≤30 minutos.

## Prerequisitos (5 minutos)

### 1. Verificar Instalación

```bash
# Verificar Python
python3 --version  # Debe ser 3.11 o 3.12

# Verificar Node.js
node --version  # Debe ser 20+

# Verificar Poetry
poetry --version

# Verificar pnpm
pnpm --version
```

### 2. Clonar y Configurar

```bash
# Clonar repositorio
git clone <repository-url>
cd "One Smart Trade"

# Backend
cd backend
poetry install
cp .env.example .env  # Si existe

# Frontend
cd ../frontend
pnpm install
```

## Inicio Rápido (10 minutos)

### 1. Iniciar Backend

```bash
cd backend
poetry run uvicorn app.main:app --reload --port 8000
```

**Verificar**: Abrir http://localhost:8000/docs - Debe mostrar Swagger UI

### 2. Iniciar Frontend (Opcional)

```bash
cd frontend
pnpm run dev
```

**Verificar**: Abrir http://localhost:5173 - Debe mostrar dashboard

### 3. Verificar Pipeline

```bash
# Verificar que el servicio está corriendo
curl http://localhost:8000/health

# Ver última recomendación (si existe)
curl http://localhost:8000/api/v1/recommendation/today | jq
```

## Operación Básica (10 minutos)

### Obtener Recomendación del Día

**Opción 1: Via API**
```bash
curl http://localhost:8000/api/v1/recommendation/today | jq '{
  signal: .signal,
  confidence: .confidence,
  entry: .entry_range.optimal,
  sl: .stop_loss_take_profit.stop_loss,
  tp: .stop_loss_take_profit.take_profit,
  execution_plan: .execution_plan != null
}'
```

**Opción 2: Via Frontend**
- Abrir http://localhost:5173
- Ver recomendación en dashboard principal

**Opción 3: Via Python**
```bash
cd backend
poetry run python -c "
import asyncio
from app.services.recommendation_service import RecommendationService

async def get_today():
    service = RecommendationService()
    result = await service.get_today_recommendation(allow_replay=True)
    if result:
        print(f'Signal: {result.get(\"signal\")}')
        print(f'Entry: {result.get(\"entry_range\", {}).get(\"optimal\")}')
        exec_plan = result.get('execution_plan', {})
        if exec_plan:
            print(f'\\nExecution Plan:')
            print(exec_plan.get('instructions', '')[:500])
    else:
        print('No recommendation available')

asyncio.run(get_today())
"
```

### Generar Nueva Recomendación (Si no existe)

```bash
cd backend
poetry run python -c "
import asyncio
from app.services.recommendation_service import RecommendationService

async def generate():
    service = RecommendationService()
    result = await service.generate_recommendation()
    if result:
        print(f'✅ Generated: {result.get(\"signal\")}')
        print(f'   ID: {result.get(\"id\")}')
    else:
        print('❌ Generation failed')

asyncio.run(generate())
"
```

### Ejecutar Paper Trading

Ver guía completa: [Paper Trading Playbook](PAPER_TRADING_PLAYBOOK.md)

**Resumen rápido**:
1. Obtener recomendación (ver arriba)
2. Revisar `execution_plan` en la respuesta
3. Ejecutar orden en exchange de paper trading
4. Configurar SL/TP inmediatamente
5. Monitorear posición

## Comandos Esenciales (5 minutos)

### Verificar Estado del Sistema

```bash
# Health check
curl http://localhost:8000/health

# Última recomendación
curl http://localhost:8000/api/v1/recommendation/today

# Historial
curl http://localhost:8000/api/v1/recommendation/history?limit=5
```

### Verificar Datos

```bash
cd backend
poetry run python -c "
from app.data.curation import DataCuration
curation = DataCuration()
df_1h = curation.load_curated('binance', 'BTCUSDT', '1h')
df_1d = curation.load_curated('binance', 'BTCUSDT', '1d')
print(f'1h: {len(df_1h)} rows, latest: {df_1h.index[-1]}')
print(f'1d: {len(df_1d)} rows, latest: {df_1d.index[-1]}')
"
```

### Ejecutar Auditoría

```bash
cd backend
poetry run python backend/app/scripts/preflight_audit.py --generate
```

### Ver Logs

```bash
# Ver logs en tiempo real
tail -f backend/logs/app.log

# Buscar errores
grep -i error backend/logs/app.log | tail -20

# Ver pipeline diario
grep "Pipeline.*Signal generated" backend/logs/app.log | tail -5
```

## Troubleshooting Rápido

### Problema: "No recommendation available"

**Solución**:
```bash
# Generar manualmente
cd backend
poetry run python -c "
import asyncio
from app.services.recommendation_service import RecommendationService
service = RecommendationService()
result = asyncio.run(service.generate_recommendation())
print('Generated' if result else 'Failed')
"
```

### Problema: "Data is stale"

**Solución**:
```bash
# Verificar última ingesta
tail -20 backend/logs/app.log | grep ingestion

# Forzar ingesta manual (si scheduler no está corriendo)
cd backend
poetry run python -m app.data.ingestion
```

### Problema: Servicio no responde

**Solución**:
```bash
# Verificar que está corriendo
ps aux | grep uvicorn

# Reiniciar si es necesario
cd backend
poetry run uvicorn app.main:app --reload --port 8000
```

## Recursos de Aprendizaje

### Documentación Completa

1. **Flujo E2E**: [E2E_FLOW.md](E2E_FLOW.md) - Entender cómo funciona el sistema
2. **Paper Trading**: [PAPER_TRADING_PLAYBOOK.md](PAPER_TRADING_PLAYBOOK.md) - Ejecutar trading manual
3. **Runbooks**: [runbooks/](runbooks/) - Guías operativas

### Comandos Útiles

```bash
# Ver todas las recomendaciones
curl http://localhost:8000/api/v1/recommendation/history?limit=10

# Ver métricas de performance
curl http://localhost:8000/api/v1/performance/summary

# Validar SL/TP
curl "http://localhost:8000/api/v1/sltp-validation/weekly-report?weeks_back=1"

# Ver configuración
cat backend/app/core/config.py | grep -A 5 "class Settings"
```

## Checklist de Onboarding

- [ ] Sistema instalado y corriendo
- [ ] Backend responde en http://localhost:8000
- [ ] Puedo obtener recomendación del día
- [ ] Entiendo el execution plan
- [ ] Sé cómo ejecutar paper trading
- [ ] Sé cómo verificar logs
- [ ] Sé cómo generar recomendación manualmente
- [ ] He leído el Paper Trading Playbook
- [ ] Sé dónde encontrar documentación

## Próximos Pasos

1. **Ejecutar primer paper trade**: Sigue el [Paper Trading Playbook](PAPER_TRADING_PLAYBOOK.md)
2. **Entender el flujo completo**: Lee [E2E_FLOW.md](E2E_FLOW.md)
3. **Familiarizarse con runbooks**: Revisa [runbooks/](runbooks/)
4. **Configurar monitoreo**: Setup alertas y métricas

## Soporte

- **Documentación**: `docs/`
- **Logs**: `backend/logs/app.log`
- **API Docs**: http://localhost:8000/docs
- **Runbooks**: `docs/runbooks/`

## Tiempo Total Estimado

- **Instalación**: 5 minutos
- **Inicio rápido**: 10 minutos
- **Operación básica**: 10 minutos
- **Comandos esenciales**: 5 minutos
- **Total**: ~30 minutos

¡Listo para operar! 🚀

