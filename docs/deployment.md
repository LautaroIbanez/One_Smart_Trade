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
- Ver `backend/.env.example`

## Observabilidad
- Métricas en `/metrics` (Prometheus scrape target)
- Logs JSON a stdout (colectar con journald o Filebeat)

## Alertas
- Webhook: `scripts/alerts/webhook_alert.py`
- Email: `scripts/alerts/email_alert.py`

