# Runbook: Datos Incompletos

## Síntomas
- Gaps en datos históricos
- Métricas `ost_data_gaps_total` incrementando
- Señales no generadas por falta de datos
- Logs muestran "Insufficient data" o "No data in date range"

## Diagnóstico

### 1. Verificar gaps en datos
```bash
cd /opt/one-smart-trade/backend
poetry run python -m app.scripts.check_gaps --interval all --days 30
```

O para un intervalo específico:
```bash
poetry run python -m app.scripts.check_gaps --interval 1d --days 30
```

### 2. Verificar logs de ingesta
```bash
journalctl -u one-smart-trade-backend -n 500 --no-pager | grep -i "gap\|incomplete\|missing"
```

### 3. Verificar métricas
```bash
curl -s http://localhost:8000/metrics | grep ost_data_gaps_total
```

## Mitigación

### Paso 1: Backfill manual
```bash
cd /opt/one-smart-trade/backend
# Backfill todos los intervalos (últimos 30 días por defecto)
poetry run python -m app.scripts.backfill --interval all --days 30

# O para un intervalo específico
poetry run python -m app.scripts.backfill --interval 1d --days 30
```

### Paso 2: Verificar datos raw
```bash
# Verificar archivos Parquet
ls -lh data/raw/*/
# Verificar tamaño y fechas de modificación
```

### Paso 3: Regenerar datos curados
```bash
cd /opt/one-smart-trade/backend
# Curar todos los intervalos
poetry run python -m app.scripts.curate --interval all

# O para un intervalo específico
poetry run python -m app.scripts.curate --interval 1d
```

### Paso 4: Si gaps persisten
- Verificar conectividad a Binance
- Verificar espacio en disco
- Verificar permisos de escritura en `data/`
- Considerar usar datos históricos alternativos

## Criterios de Salida
- ✅ Datos completos para últimos 30 días
- ✅ No gaps detectados en validación
- ✅ Señales se generan correctamente
- ✅ Métricas `ost_data_gaps_total` estables

## Prevención
- Validación de gaps en pipeline de ingesta
- Backfill automático en detección de gaps
- Alertas cuando gaps > 24 horas
- Monitoreo de espacio en disco
