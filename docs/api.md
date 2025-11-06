# API Specification - One Smart Trade

## Base URL
```
http://localhost:8000
```

## Authentication
No authentication required (public API).

## Rate Limiting
- 300 requests per minute per IP
- Returns `429 Too Many Requests` when exceeded

## Endpoints

### GET `/`
Health check endpoint.

**Response:**
```json
{
  "status": "ok",
  "service": "One Smart Trade API",
  "version": "0.1.0"
}
```

### GET `/health`
Detailed health check.

**Response:**
```json
{
  "status": "healthy"
}
```

### GET `/metrics`
Prometheus metrics endpoint.

**Response:** Prometheus text format

---

### GET `/api/v1/recommendation/today`
Get today's trading recommendation.

**Response:**
```json
{
  "signal": "BUY|HOLD|SELL",
  "entry_range": {
    "min": 45000.0,
    "max": 45500.0,
    "optimal": 45250.0
  },
  "stop_loss_take_profit": {
    "stop_loss": 44000.0,
    "take_profit": 47000.0,
    "stop_loss_pct": -2.21,
    "take_profit_pct": 3.87
  },
  "confidence": 72.5,
  "current_price": 45200.0,
  "analysis": "Contexto alcista...",
  "indicators": {
    "rsi": 58.3,
    "macd": 0.0023,
    "atr": 850.5,
    "adx": 28.7,
    "momentum": 125.0
  },
  "risk_metrics": {
    "risk_reward_ratio": 1.75,
    "sl_probability": 30.0,
    "tp_probability": 50.0,
    "expected_drawdown": 250.0,
    "volatility": 35.2
  },
  "timestamp": "2024-01-15T12:00:00",
  "disclaimer": "This is not financial advice..."
}
```

**Status Codes:**
- `200`: Success
- `404`: No recommendation available for today
- `500`: Internal server error

---

### GET `/api/v1/recommendation/history`
Get recent recommendation history.

**Query Parameters:**
- `limit` (optional, default: 10): Number of recommendations to return

**Response:**
```json
{
  "recommendations": [
    {
      "signal": "BUY",
      "entry_range": {...},
      "stop_loss_take_profit": {...},
      "confidence": 72.5,
      "current_price": 45200.0,
      "timestamp": "2024-01-15T12:00:00",
      "disclaimer": "..."
    }
  ],
  "count": 10
}
```

**Status Codes:**
- `200`: Success
- `500`: Internal server error

---

### GET `/api/v1/diagnostics/last-run`
Get information about last scheduler runs.

**Response:**
```json
{
  "last_ingestion": "2024-01-15T11:45:00",
  "last_signal": "2024-01-15T12:00:00",
  "status": "ok"
}
```

**Status Codes:**
- `200`: Success

---

### GET `/api/v1/market/{interval}`
Get market data for a specific interval.

**Path Parameters:**
- `interval`: One of `15m`, `30m`, `1h`, `4h`, `1d`, `1w`

**Response:**
```json
{
  "interval": "1h",
  "status": "success",
  "current_price": 45200.0,
  "volume": 1250.5,
  "vwap": 45150.0,
  "atr": 850.5,
  "volatility": 0.35,
  "support": 44800.0,
  "resistance": 45600.0,
  "timestamp": "2024-01-15T12:00:00"
}
```

**Status Codes:**
- `200`: Success
- `400`: Invalid interval
- `500`: Internal server error

---

### GET `/api/v1/performance/summary`
Get backtesting performance summary.

**Response:**
```json
{
  "status": "success",
  "metrics": {
    "cagr": 15.5,
    "sharpe": 1.2,
    "sortino": 1.5,
    "max_drawdown": 12.3,
    "win_rate": 58.5,
    "profit_factor": 1.8,
    "expectancy": 125.0,
    "calmar": 1.26,
    "total_return": 75.5,
    "total_trades": 150,
    "winning_trades": 88,
    "losing_trades": 62
  },
  "period": {
    "start": "2019-01-01T00:00:00",
    "end": "2024-01-15T00:00:00"
  },
  "report_path": "./data/backtest_reports/backtest-report.md",
  "disclaimer": "This is not financial advice..."
}
```

**Status Codes:**
- `200`: Success
- `500`: Internal server error

---

## Error Responses

All errors follow this format:

```json
{
  "error": "Error message",
  "status_code": 500
}
```

For validation errors:
```json
{
  "error": "Validation error",
  "details": [...]
}
```

## Scheduler Recovery Procedures

### If scheduler fails to start:
1. Check logs: `journalctl -u one-smart-trade-backend -n 100`
2. Verify database: `sqlite3 data/trading.db "SELECT * FROM run_logs ORDER BY finished_at DESC LIMIT 5;"`
3. Restart service: `sudo systemctl restart one-smart-trade-backend`

### If ingestion job fails:
1. Check last run: `GET /api/v1/diagnostics/last-run`
2. Manually trigger ingestion:
```bash
cd backend
python -c "
import asyncio
from app.data.ingestion import DataIngestion
di = DataIngestion()
result = asyncio.run(di.ingest_all_timeframes())
print(result)
"
```
3. Check Binance API status: `curl https://api.binance.com/api/v3/ping`

### If signal generation fails:
1. Verify curated data exists:
```bash
cd backend
python -c "
from app.data.curation import DataCuration
dc = DataCuration()
df_1d = dc.get_latest_curated('1d')
df_1h = dc.get_latest_curated('1h')
print(f'1d available: {df_1d is not None and not df_1d.empty}')
print(f'1h available: {df_1h is not None and not df_1h.empty}')
"
```
2. Manually generate signal:
```bash
cd backend
python -c "
import asyncio
from app.main import job_generate_signal
asyncio.run(job_generate_signal())
"
```

### If scheduler jobs are not running:
1. Check scheduler status in logs
2. Verify timezone configuration: `SCHEDULER_TIMEZONE=UTC`
3. Check system time: `date -u`
4. Restart service to reinitialize scheduler

