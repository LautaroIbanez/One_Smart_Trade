# Despliegue Manual (sin Docker)

## Requisitos
- Python 3.11/3.12, Poetry
- Node 20, pnpm
- Systemd (Linux)

## Backend (Systemd)

Archivo de servicio `one-smart-trade-backend.service`:
```ini
[Unit]
Description=One Smart Trade Backend
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/one-smart-trade/backend
Environment=PYTHONUNBUFFERED=1
Environment=DATABASE_URL=sqlite:///./data/trading.db
Environment=BINANCE_API_BASE_URL=https://api.binance.com/api/v3
Environment=LOG_LEVEL=INFO
Environment=SCHEDULER_TIMEZONE=UTC
Environment=RECOMMENDATION_UPDATE_TIME=12:00
ExecStart=/usr/bin/poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
User=ost
Group=ost

[Install]
WantedBy=multi-user.target
```

Instalación:
```bash
sudo cp one-smart-trade-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now one-smart-trade-backend
```

## Timers para Backups

Ejemplo de timer para backup diario (si aplica BD externa):
```ini
# /etc/systemd/system/ost-backup.service
[Unit]
Description=OST Backup

[Service]
Type=oneshot
ExecStart=/opt/one-smart-trade/scripts/backup.sh
```
```ini
# /etc/systemd/system/ost-backup.timer
[Unit]
Description=OST Backup Timer

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

## Nginx (opcional)

Proxy para `/api` y servir frontend build (`frontend/dist`):
```nginx
server {
  listen 80;
  server_name _;

  location /api/ {
    proxy_pass http://127.0.0.1:8000/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
  }

  location / {
    root /opt/one-smart-trade/frontend/dist;
    try_files $uri /index.html;
  }
}
```

## Variables de Entorno

Crear archivo `.env` en `backend/`:
```bash
DATABASE_URL=sqlite:///./data/trading.db
BINANCE_API_BASE_URL=https://api.binance.com/api/v3
LOG_LEVEL=INFO
SCHEDULER_TIMEZONE=UTC
RECOMMENDATION_UPDATE_TIME=12:00
DATA_DIR=./data
CORS_ORIGINS=["http://localhost:5173","http://localhost:3000"]
```

### Variables Opcionales para Alertas
```bash
ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
ALERT_TO=alerts@example.com
```

## Observabilidad

### Métricas Prometheus
- Endpoint: `http://localhost:8000/metrics`
- Scrape interval recomendado: 15s
- Métricas clave:
  - `ost_http_requests_total`: Total de requests HTTP
  - `ost_http_request_latency_seconds`: Latencia de requests
  - `ost_ingestion_duration_seconds`: Duración de ingesta
  - `ost_ingestion_failures_total`: Fallos de ingesta
  - `ost_signal_generation_duration_seconds`: Duración de generación de señal
  - `ost_last_ingestion_timestamp_seconds`: Timestamp de última ingesta
  - `ost_last_signal_timestamp_seconds`: Timestamp de última señal

### Logging JSON Estructurado
Los logs se escriben a stdout en formato JSON. Configurar journald para capturar:
```ini
# /etc/systemd/journald.conf
[Journal]
Storage=persistent
MaxRetentionSec=30day
```

O usar Filebeat/Logstash para enviar a Elasticsearch.

### Rotación de Logs
Configurar logrotate para logs en archivo (si se redirigen):
```bash
# /etc/logrotate.d/one-smart-trade
/var/log/one-smart-trade/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0640 ost ost
}
```

## Alertas

### Health Check Automático
Configurar cron o systemd timer para ejecutar checks:
```ini
# /etc/systemd/system/ost-healthcheck.service
[Unit]
Description=OST Health Check

[Service]
Type=oneshot
WorkingDirectory=/opt/one-smart-trade
ExecStart=/usr/bin/python3 scripts/alerts/check_alerts.py
EnvironmentFile=/opt/one-smart-trade/backend/.env
```

```ini
# /etc/systemd/system/ost-healthcheck.timer
[Unit]
Description=OST Health Check Timer

[Timer]
OnCalendar=*/15 * * * *  # Cada 15 minutos
Persistent=true

[Install]
WantedBy=timers.target
```

Activar:
```bash
sudo systemctl enable --now ost-healthcheck.timer
```

### Alertas Manuales
```bash
# Webhook
export ALERT_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
export ALERT_MESSAGE="Test alert"
python scripts/alerts/webhook_alert.py

# Email
export SMTP_HOST=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USER=your-email@gmail.com
export SMTP_PASSWORD=your-password
export ALERT_TO=alerts@example.com
export ALERT_BODY="Test alert body"
python scripts/alerts/email_alert.py
```

## Recuperación tras Reinicio

### Verificar Estado
```bash
# Estado del servicio
sudo systemctl status one-smart-trade-backend

# Verificar última ingesta
curl -s http://localhost:8000/api/v1/diagnostics/last-run

# Verificar métricas
curl -s http://localhost:8000/metrics | grep ost_last
```

### Si datos faltan tras reinicio
```bash
# Ejecutar ingesta manual
cd /opt/one-smart-trade/backend
python -c "
import asyncio
from app.data.ingestion import DataIngestion
asyncio.run(DataIngestion().ingest_all_timeframes())
"
```

### Backup y Restauración

#### Backup de Base de Datos
```bash
# Backup manual
cp data/trading.db data/trading.db.backup.$(date +%Y%m%d_%H%M%S)

# Backup automático (systemd timer)
# /etc/systemd/system/ost-backup.service
[Unit]
Description=OST Database Backup

[Service]
Type=oneshot
ExecStart=/bin/bash -c 'cp /opt/one-smart-trade/backend/data/trading.db /opt/one-smart-trade/backups/trading.db.$(date +%%Y%%m%%d_%%H%%M%%S)'
```

#### Restaurar Backup
```bash
# Detener servicio
sudo systemctl stop one-smart-trade-backend

# Restaurar
cp data/trading.db.backup.YYYYMMDD_HHMMSS data/trading.db

# Reiniciar
sudo systemctl start one-smart-trade-backend
```

## Monitoreo Recomendado

### Dashboards Prometheus/Grafana
- Latencia de API (p50, p95, p99)
- Tasa de errores HTTP
- Duración de ingesta por timeframe
- Tasa de fallos de señal
- Última ejecución de jobs

### Alertas Recomendadas
- Ingesta no ejecutada en >30 minutos
- Señal no generada en >25 horas
- Latencia p95 > 5 segundos
- Tasa de errores > 5%
- Espacio en disco < 10%

## Troubleshooting

Ver runbooks en `docs/runbooks/`:
- `binance_down.md`: Binance API caído
- `data_incomplete.md`: Datos incompletos
- `calc_failure.md`: Fallo de cálculo
- `metrics_degradation.md`: Degradación de métricas

