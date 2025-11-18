# Runbooks - One Smart Trade

Runbooks para operación y resolución de incidentes comunes.

## Scripts CLI Disponibles

El proyecto incluye scripts CLI para operaciones manuales comunes:

- **`python -m app.scripts.backfill`**: Backfill de datos históricos
  - `--interval {15m|30m|1h|4h|1d|1w}`: Intervalo a backfillear (requerido)
  - `--since YYYY-MM-DD`: Fecha desde la cual backfillear (opcional)

- **`python -m app.scripts.check_gaps`**: Verificar gaps en datos
  - `--interval {15m|30m|1h|4h|1d|1w|all}`: Intervalo a verificar (default: all)
  - `--days N`: Número de días a verificar (default: 30)

- **`python -m app.scripts.curate`**: Regenerar datos curados
  - `--interval {15m|30m|1h|4h|1d|1w|all}`: Intervalo a curar (default: all)

- **`python -m app.scripts.regenerate_signal`**: Regenerar señal manualmente
  - Sin parámetros

- **`python -m app.backtesting.run_campaign`**: Ejecutar campañas walk-forward con persistencia de métricas
  - `--start YYYY-MM-DD --end YYYY-MM-DD`
  - `--walk-forward-window N` (días)
  - `--cost-bps X` (comisión base en bps)

**Ejemplo de uso:**
```bash
cd /opt/one-smart-trade/backend
poetry run python -m app.scripts.backfill --interval 1d --since 2024-01-01
poetry run python -m app.scripts.check_gaps --interval all --days 7
poetry run python -m app.scripts.regenerate_signal
```

## Recalcular parquet y versionado de datasets

1. **Versionar estado actual**  
   ```bash
   cd backend
   for interval in 15m 30m 1h 4h 1d 1w; do
       cp data/curated/$interval/latest.parquet data/curated/$interval/$(date +%Y%m%d)_pre-factor-upgrade.parquet
   done
   ```
   Ajusta el sufijo (`pre-factor-upgrade`) según el experimento que compares.
2. **Regenerar con los nuevos indicadores**  
   ```bash
   poetry run python -m app.scripts.curate --interval all
   ```
   Usa `--interval <tf>` para recalcular solo un timeframe.
3. **Versionar resultado post-curación**  
   ```bash
   for interval in 15m 30m 1h 4h 1d 1w; do
       cp data/curated/$interval/latest.parquet data/curated/$interval/$(date +%Y%m%d)_post-factor-upgrade.parquet
   done
   ```
4. **Comparar señales antes/después**  
   - Point the quant engine scripts (`app.quant`) to the versioned parquet deseado.
   - Corre `poetry run pytest tests/quant/test_indicators_and_factors.py` para asegurar consistencia.

### Notas operativas

- Si tu entorno no soporta `date`, reemplaza el prefijo por una marca manual (`20250115`).
- Mantén como mínimo dos versiones recientes para diagnósticos; archiva versiones antiguas en almacenamiento frío.

## Índice

### Operaciones Diarias

1. [Generación de Señal Diaria](daily_signal_generation.md) - Pipeline diario y troubleshooting

### Incidentes Operacionales

2. [Binance API Down](binance_down.md)
3. [Datos Incompletos](data_incomplete.md)
4. [Cálculo de Recomendación Fallido](calc_failure.md)
5. [Degradación de Métricas](metrics_degradation.md)
6. [Latencia Excesiva](#latencia-excesiva)
7. [Base de Datos Corrupta](#base-de-datos-corrupta)

### Flujos Automáticos

8. [Flujos Automáticos](automated_flows.md)
   - Ingesta → Clasificación de Régimen
   - Trigger de Recalibración
   - Redeploy de Parámetros

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
curl -s http://localhost:8000/metrics | grep ingestion_failure_total
```

### Solución
1. Identificar timeframe afectado usando `check_gaps`
2. Ejecutar backfill manual para timeframe:
   ```bash
   cd backend
   poetry run python -m app.scripts.backfill --interval 1h --since 2024-01-01
   ```
3. Regenerar datos curados (se hace automáticamente en backfill, pero se puede hacer manualmente):
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
   poetry run python -m app.scripts.backfill --interval 1d --since 2024-01-01
   poetry run python -m app.scripts.backfill --interval 1h --since 2024-01-01
   
   # Curar datos (se hace automáticamente en backfill, pero se puede hacer manualmente)
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

