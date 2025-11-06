# Runbooks - One Smart Trade

Runbooks para operación y resolución de incidentes comunes.

## Scripts CLI Disponibles

El proyecto incluye scripts CLI para operaciones manuales comunes:

- **`python -m app.scripts.backfill`**: Backfill de datos históricos
  - `--interval {15m|30m|1h|4h|1d|1w|all}`: Intervalo a backfillear (default: all)
  - `--days N`: Número de días a backfillear (default: 30)

- **`python -m app.scripts.check_gaps`**: Verificar gaps en datos
  - `--interval {15m|30m|1h|4h|1d|1w|all}`: Intervalo a verificar (default: all)
  - `--days N`: Número de días a verificar (default: 30)

- **`python -m app.scripts.curate`**: Regenerar datos curados
  - `--interval {15m|30m|1h|4h|1d|1w|all}`: Intervalo a curar (default: all)

- **`python -m app.scripts.regenerate_signal`**: Regenerar señal manualmente
  - Sin parámetros

**Ejemplo de uso:**
```bash
cd /opt/one-smart-trade/backend
poetry run python -m app.scripts.backfill --interval 1d --days 30
poetry run python -m app.scripts.check_gaps --interval all --days 7
poetry run python -m app.scripts.regenerate_signal
```

## Índice

1. [Binance API Down](binance_down.md)
2. [Datos Incompletos](data_incomplete.md)
3. [Cálculo de Recomendación Fallido](calc_failure.md)
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
# Verificar gaps en datos usando script CLI
cd backend
poetry run python -m app.scripts.check_gaps --interval 1h --days 30

# O verificar todos los intervalos
poetry run python -m app.scripts.check_gaps --interval all --days 30

# Revisar última ingesta
curl -s http://localhost:8000/api/v1/diagnostics/last-run

# Verificar métricas de Prometheus
curl -s http://localhost:8000/metrics | grep ost_last_ingestion_timestamp_seconds
```

### Solución
1. Identificar timeframe afectado usando `check_gaps`
2. Ejecutar backfill manual para timeframe:
   ```bash
   cd backend
   poetry run python -m app.scripts.backfill --interval 1h --days 30
   ```
3. Regenerar datos curados:
   ```bash
   poetry run python -m app.scripts.curate --interval 1h
   ```
4. Verificar que los gaps se resolvieron:
   ```bash
   poetry run python -m app.scripts.check_gaps --interval 1h --days 30
   ```
5. Regenerar recomendación si necesario:
   ```bash
   poetry run python -m app.scripts.regenerate_signal
   ```

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
1. Identificar error específico en logs:
   ```bash
   tail -f backend/logs/app.log | grep -i error
   ```
2. Verificar disponibilidad de datos:
   ```bash
   cd backend
   poetry run python -c "
   from app.data.curation import DataCuration
   dc = DataCuration()
   df_1d = dc.get_latest_curated('1d')
   df_1h = dc.get_latest_curated('1h')
   print(f'1d: {len(df_1d) if df_1d is not None else 0} rows')
   print(f'1h: {len(df_1h) if df_1h is not None else 0} rows')
   "
   ```
3. Si faltan datos, regenerar:
   ```bash
   # Backfill si es necesario
   poetry run python -m app.scripts.backfill --interval 1d --days 7
   poetry run python -m app.scripts.backfill --interval 1h --days 7
   
   # Curar datos
   poetry run python -m app.scripts.curate --interval 1d
   poetry run python -m app.scripts.curate --interval 1h
   ```
4. Recalcular señal manualmente:
   ```bash
   poetry run python -m app.scripts.regenerate_signal
   ```
5. Verificar que la señal se generó:
   ```bash
   curl http://localhost:8000/api/v1/recommendation/today
   ```
6. Si persiste, revisar configuración y datos de entrada

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

