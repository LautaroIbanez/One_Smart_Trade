# Runbook: Binance API caído

## Síntomas
- Errores 5xx o timeouts desde Binance
- Ingesta falla repetidamente

## Diagnóstico
```bash
curl -s https://api.binance.com/api/v3/ping
journalctl -u one-smart-trade-backend -n 200 --no-pager | grep -i binance
```

## Mitigación
1. Pausar scheduler de ingesta si hay tormenta de errores.
   - Temporariamente deshabilitar job de ingesta (comentar en `app.main` o usar `scheduler.pause_job('ingest_all')`).
2. Esperar 5-15 minutos y reintentar manualmente:
```bash
python -c "import asyncio;from app.data.ingestion import DataIngestion;asyncio.run(DataIngestion().ingest_all_timeframes())"
```
3. Si persiste >30m, notificar por webhook:
```bash
ALERT_WEBHOOK_URL=<url> ALERT_MESSAGE="Binance down" python scripts/alerts/webhook_alert.py
```

## Prevención
- Backoff exponencial activo
- Cache de último dataset válido

