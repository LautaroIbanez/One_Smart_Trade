# Runbook: Degradación de Métricas

## Síntomas
- Latencia de API incrementando
- Tasa de errores HTTP incrementando
- Tiempo de ingesta incrementando
- Memoria/CPU alto

## Diagnóstico

### 1. Verificar métricas Prometheus
```bash
# Latencia promedio
curl -s http://localhost:8000/metrics | grep ost_http_request_latency_seconds

# Tasa de errores
curl -s http://localhost:8000/metrics | grep ost_http_requests_total | grep status=5

# Duración de ingesta
curl -s http://localhost:8000/metrics | grep ost_ingestion_duration_seconds
```

### 2. Verificar recursos del sistema
```bash
# CPU y memoria
top -p $(pgrep -f "uvicorn app.main")

# Espacio en disco
df -h /opt/one-smart-trade

# Tamaño de base de datos
du -sh data/trading.db
```

### 3. Verificar logs de performance
```bash
journalctl -u one-smart-trade-backend -n 500 --no-pager | grep -i "slow\|timeout\|memory"
```

## Mitigación

### Paso 1: Identificar cuello de botella
```bash
# Verificar queries lentas en BD
sqlite3 data/trading.db "EXPLAIN QUERY PLAN SELECT * FROM recommendations ORDER BY created_at DESC LIMIT 10;"

# Verificar tamaño de tablas
sqlite3 data/trading.db "SELECT name, COUNT(*) FROM recommendations; SELECT name, COUNT(*) FROM run_logs;"
```

### Paso 2: Limpiar datos antiguos (si necesario)
```bash
python -c "
from app.core.database import SessionLocal
from app.db.models import RecommendationORM, RunLogORM
from datetime import datetime, timedelta
from sqlalchemy import delete

cutoff = datetime.utcnow() - timedelta(days=90)
with SessionLocal() as db:
    # Limpiar recomendaciones antiguas (mantener últimas 90 días)
    db.execute(delete(RecommendationORM).where(RecommendationORM.created_at < cutoff))
    # Limpiar logs antiguos (mantener últimos 30 días)
    db.execute(delete(RunLogORM).where(RunLogORM.finished_at < cutoff))
    db.commit()
    print('Cleanup completed')
"
```

### Paso 3: Reiniciar servicio
```bash
sudo systemctl restart one-smart-trade-backend
# Monitorear después del reinicio
journalctl -u one-smart-trade-backend -f
```

### Paso 4: Si persiste, escalar recursos
- Aumentar workers de uvicorn
- Aumentar memoria disponible
- Considerar migrar a PostgreSQL si SQLite es cuello de botella

## Criterios de Salida
- ✅ Latencia < 1 segundo (p95)
- ✅ Tasa de errores < 1%
- ✅ Ingesta completa en < 5 minutos
- ✅ Uso de memoria estable

## Prevención
- Monitoreo continuo de métricas
- Alertas automáticas en degradación
- Limpieza periódica de datos antiguos
- Optimización de queries y índices

