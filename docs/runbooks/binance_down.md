# Runbook: Binance API caído

## Síntomas
- Errores 5xx o timeouts desde Binance
- Ingesta falla repetidamente
- Métricas `ost_ingestion_failures_total` incrementando
- Logs muestran `ConnectionError`, `TimeoutError`, o `HTTPStatusError`

## Diagnóstico

### 1. Verificar estado de Binance
```bash
# Ping a Binance
curl -s https://api.binance.com/api/v3/ping
# Debe retornar {} si está operativo

# Verificar status page (si existe)
curl -s https://www.binance.com/en/support/announcement
```

### 2. Revisar logs del servicio
```bash
# Ver últimos logs
journalctl -u one-smart-trade-backend -n 200 --no-pager | grep -i binance

# Ver errores recientes
journalctl -u one-smart-trade-backend -n 500 --no-pager | grep -i "error\|exception\|failed"
```

### 3. Verificar métricas Prometheus
```bash
# Consultar métricas de fallos
curl -s http://localhost:8000/metrics | grep ost_ingestion_failures_total

# Ver última ingesta exitosa
curl -s http://localhost:8000/metrics | grep ost_last_ingestion_timestamp_seconds
```

## Mitigación

### Paso 1: Pausar scheduler (si hay tormenta de errores)
```bash
# Opción A: Pausar job específico (requiere acceso a código)
# Editar backend/app/main.py y comentar temporalmente:
# scheduler.add_job(job_ingest_all, "interval", minutes=15, id="ingest_all")

# Opción B: Reiniciar servicio con scheduler deshabilitado
sudo systemctl stop one-smart-trade-backend
# Editar .env y añadir: DISABLE_SCHEDULER=true
sudo systemctl start one-smart-trade-backend
```

### Paso 2: Esperar y reintentar
Esperar 5-15 minutos y probar manualmente:
```bash
cd /opt/one-smart-trade/backend
# Reintentar ingesta de todos los intervalos
poetry run python -m app.scripts.backfill --interval all --days 1

# O para un intervalo específico
poetry run python -m app.scripts.backfill --interval 1d --days 1
```

### Paso 3: Si persiste >30 minutos
Enviar alerta:
```bash
export ALERT_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
export ALERT_MESSAGE="Binance API down for >30 minutes. Manual intervention required."
python scripts/alerts/webhook_alert.py
```

### Paso 4: Usar datos en cache
El sistema puede operar con datos en cache por varias horas. Verificar:
```bash
cd /opt/one-smart-trade/backend
# Verificar datos disponibles usando script de gaps
poetry run python -m app.scripts.check_gaps --interval 1d --days 7
```

## Criterios de Salida
- ✅ Binance API responde a `/ping`
- ✅ Ingesta manual exitosa
- ✅ Métricas `ost_ingestion_failures_total` no incrementan
- ✅ Logs muestran ingesta exitosa

## Escalación
- **< 15 min:** Normal, backoff automático maneja
- **15-30 min:** Monitorear, no acción requerida
- **30-60 min:** Enviar alerta, considerar pausar scheduler
- **> 60 min:** Escalar a equipo, considerar usar datos alternativos o backup

## Prevención
- Backoff exponencial activo (implementado en `binance_client.py`)
- Cache de último dataset válido (Parquet persistido)
- Timeouts configurados (30s por request)
- Retry automático con límite de 3 intentos

