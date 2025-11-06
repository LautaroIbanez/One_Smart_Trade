# Runbook: Fallo en cálculo de recomendación

## Síntomas
- `/api/v1/recommendation/today` retorna 500 o 404 prolongado
- `diagnostics/last-run` no muestra signal reciente

## Diagnóstico
```bash
curl -s http://localhost:8000/api/v1/diagnostics/last-run | jq .
journalctl -u one-smart-trade-backend -n 200 --no-pager | grep -i error
```

## Mitigación
1. Verificar datos curated (1d y 1h):
```bash
python - << 'PY'
from app.data.curation import DataCuration
print('1d exists:', DataCuration().get_latest_curated('1d') is not None)
print('1h exists:', DataCuration().get_latest_curated('1h') is not None)
PY
```
2. Recalcular recomendación manual:
```bash
python - << 'PY'
from app.data.curation import DataCuration
from app.quant.signal_engine import generate_signal

dc = DataCuration()
rec = generate_signal(dc.get_latest_curated('1h') or dc.get_latest_curated('1d'), dc.get_latest_curated('1d'))
print(rec)
PY
```
3. Si persiste, emitir alerta:
```bash
ALERT_WEBHOOK_URL=<url> ALERT_MESSAGE="Signal generation failed" python scripts/alerts/webhook_alert.py
```

## Prevención
- Añadir checks de disponibilidad de datos antes de jobs programados
- Alertas si no se genera señal a la hora programada

