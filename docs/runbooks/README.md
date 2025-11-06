# Runbooks - One Smart Trade

Runbooks para operación y resolución de incidentes comunes.

## Índice

1. [Binance API Down](#binance-api-down)
2. [Datos Incompletos](#datos-incompletos)
3. [Cálculo de Recomendación Fallido](#cálculo-de-recomendación-fallido)
4. [Latencia Excesiva](#latencia-excesiva)
5. [Base de Datos Corrupta](#base-de-datos-corrupta)

## Binance API Down

### Síntomas
- Errores 503/504 en llamadas a Binance
- Timeouts en ingesta de datos
- Logs muestran "Connection refused" o "Service unavailable"

### Diagnóstico
```bash
# Verificar conectividad
curl https://api.binance.com/api/v3/ping

# Revisar logs
tail -f backend/logs/app.log | grep -i binance
```

### Solución
1. Verificar estado de Binance: https://www.binance.com/en/support/announcement
2. Esperar recuperación (generalmente < 5 minutos)
3. Si persiste > 15 minutos:
   - Pausar scheduler manualmente
   - Notificar al equipo
   - Considerar usar datos históricos si disponible

### Prevención
- Implementar backoff exponencial
- Cachear últimos datos válidos
- Monitorear uptime de Binance

## Datos Incompletos

### Síntomas
- Gaps en datos históricos
- Recomendaciones con confianza baja
- Errores en cálculo de indicadores

### Diagnóstico
```bash
# Verificar gaps en datos
cd backend
poetry run python -m app.data.check_gaps

# Revisar última ingesta
poetry run python -m app.data.last_ingestion_status
```

### Solución
1. Identificar timeframe afectado
2. Ejecutar ingesta manual para timeframe:
   ```bash
   poetry run python -m app.data.ingest --timeframe 1h --backfill
   ```
3. Recalcular indicadores:
   ```bash
   poetry run python -m app.indicators.recalculate --timeframe 1h
   ```
4. Regenerar recomendación si necesario

### Prevención
- Validación de gaps en pipeline
- Alertas automáticas para gaps > 1 hora
- Backfill automático en scheduler

## Cálculo de Recomendación Fallido

### Síntomas
- Endpoint `/api/v1/recommendation/today` retorna 500
- Logs muestran excepciones en cálculo
- No hay recomendación disponible

### Diagnóstico
```bash
# Revisar logs de error
tail -f backend/logs/app.log | grep -i error

# Verificar estado de datos
curl http://localhost:8000/api/v1/diagnostics/last-run
```

### Solución
1. Identificar error específico en logs
2. Verificar disponibilidad de datos:
   - Todos los timeframes tienen datos recientes
   - Indicadores calculados correctamente
3. Recalcular manualmente:
   ```bash
   poetry run python -m app.services.recommendation_service.generate_today
   ```
4. Si persiste, revisar configuración y datos de entrada

### Prevención
- Validación exhaustiva de inputs
- Manejo robusto de errores
- Tests de integración regulares

## Latencia Excesiva

### Síntomas
- Respuestas de API > 5 segundos
- Frontend muestra timeouts
- Usuarios reportan lentitud

### Diagnóstico
```bash
# Medir latencia de endpoints
time curl http://localhost:8000/api/v1/recommendation/today

# Revisar métricas de performance
curl http://localhost:8000/api/v1/diagnostics/metrics
```

### Solución
1. Identificar endpoint lento
2. Revisar queries a base de datos (N+1, falta de índices)
3. Verificar carga del sistema:
   ```bash
   top
   df -h
   ```
4. Optimizar:
   - Agregar índices a BD
   - Implementar caching
   - Optimizar queries
   - Aumentar workers si necesario

### Prevención
- Monitoreo de latencia
- Profiling regular
- Optimización continua

## Base de Datos Corrupta

### Síntomas
- Errores SQL al acceder a datos
- Integridad referencial rota
- Datos inconsistentes

### Diagnóstico
```bash
# Verificar integridad (SQLite)
cd backend/data
sqlite3 trading.db "PRAGMA integrity_check;"
```

### Solución
1. **Backup inmediato:**
   ```bash
   cp data/trading.db data/trading.db.backup
   ```
2. **Intentar reparación (SQLite):**
   ```bash
   sqlite3 trading.db ".recover" | sqlite3 trading_recovered.db
   ```
3. **Si falla, restaurar desde backup:**
   ```bash
   cp data/trading.db.backup data/trading.db
   ```
4. **Reingestar datos faltantes si necesario**

### Prevención
- Backups automáticos diarios
- Validación de integridad periódica
- Migración a PostgreSQL para producción

