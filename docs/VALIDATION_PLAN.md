# Validation Plan: FIX-01, FIX-02, FIX-03

This document provides a comprehensive validation plan to verify all fixes are working correctly.

## Quick Start

Run the automated validation script:

```bash
cd backend
python scripts/validate_fixes.py
```

Or with custom base URL:

```bash
python scripts/validate_fixes.py --base-url http://localhost:8000
```

## Manual Validation Steps

### 1. Backend Startup & Pipeline (FIX-02)

#### 1.1. Start Backend

```bash
cd backend
poetry run uvicorn app.main:app --reload --port 8000
```

**Expected:**
- Backend starts without errors
- Scheduler initializes (check logs for "Scheduler started")
- If `AUTO_RUN_PIPELINE_ON_START=True` (default), pipeline should run automatically if no recommendation exists for today

**Check logs for:**
```
INFO: Starting daily pipeline run_id=...
INFO: Pipeline ...: Ingestion completed
INFO: Pipeline ...: Curation completed
INFO: Pipeline ...: Signal generated
INFO: Initial pipeline completed successfully
```

#### 1.2. Verify Initial Pipeline

```bash
# Check if recommendation exists
curl -i http://localhost:8000/api/v1/recommendation/today
```

**Expected:**
- Status 200 with populated payload (signal, entry_range, etc.)
- OR Status 400 with `capital_missing` (normal in dev)
- OR Status 503 with `data_stale` or `no_data` (pipeline may need to run)

#### 1.3. Manual Pipeline Trigger (Optional)

If pipeline didn't run automatically:

```bash
# If ADMIN_API_KEY is set:
curl -X POST http://localhost:8000/api/v1/operational/trigger-pipeline \
  -H "X-Admin-API-Key: YOUR_KEY"

# Or if ADMIN_API_KEY is not set (dev mode):
curl -X POST http://localhost:8000/api/v1/operational/trigger-pipeline
```

**Expected:**
- Pipeline runs successfully
- New recommendation is created
- `/api/v1/recommendation/today` returns data

### 2. Endpoints (FIX-01)

#### 2.1. Today Recommendation

```bash
curl -i http://localhost:8000/api/v1/recommendation/today
```

**Expected:**
- Status 200
- Response includes: `signal`, `entry_range`, `stop_loss_take_profit`, `confidence`, `current_price`
- No 404 or 422 errors

#### 2.2. History Endpoint

```bash
curl -i 'http://localhost:8000/api/v1/recommendation/history?limit=5'
```

**Expected:**
- Status 200
- Response structure:
  ```json
  {
    "items": [...],           // NOT "recommendations"
    "next_cursor": "...",     // Optional
    "has_more": true,         // Boolean
    "insights": {...},        // Optional
    "download_url": "...",    // Optional
    "filters": {...}
  }
  ```
- Each item in `items` has: `id`, `timestamp`, `signal`, `status`, `execution_status`, etc.
- No 404 or 422 errors

#### 2.3. Performance Endpoint

```bash
curl -i 'http://localhost:8000/api/v1/recommendation/performance?lookahead_days=5&limit=30'
```

**Expected:**
- Status 200
- Response includes: `status`, `timeline`, `equity_curve`, `drawdown_curve`, `win_rate`, `average_tracking_error`, `trades_evaluated`
- May include: `equity_theoretical`, `equity_realistic`, `tracking_error_metrics`
- No 404 or 422 errors

### 3. Frontend → Backend Proxy

#### 3.1. Start Frontend

```bash
cd frontend
pnpm run dev
```

#### 3.2. Open Dashboard

Open `http://localhost:5173` in browser.

#### 3.3. Check Network Tab

Open browser DevTools → Network tab.

**Expected:**
- Requests to `/api/v1/recommendation/today` succeed (200)
- Requests to `/api/v1/recommendation/history` succeed (200)
- Requests to `/api/v1/recommendation/performance` succeed (200)
- No CORS errors
- No connection refused errors
- Data displays in UI (tables, charts populate)

### 4. Logging (FIX-03)

#### 4.1. Run Pipeline

Trigger the pipeline manually or wait for scheduled run:

```bash
curl -X POST http://localhost:8000/api/v1/operational/trigger-pipeline \
  -H "X-Admin-API-Key: YOUR_KEY"
```

#### 4.2. Check Logs

Watch backend console output or log files.

**Expected:**
- No `KeyError: Attempt to overwrite 'message'` errors
- No `KeyError: Attempt to overwrite 'status'` errors
- No `KeyError: Attempt to overwrite` errors for any reserved key
- Logs contain structured JSON with sanitized fields (e.g., `extra_message` instead of `message`)

**Look for:**
```
❌ BAD: KeyError: Attempt to overwrite 'message'
✅ GOOD: Logs show sanitized fields like "extra_message", "extra_status"
```

#### 4.3. Verify Error Context Preserved

Check that error details are still present in logs, just with renamed keys:

**Expected:**
- Error messages are preserved
- Error details are preserved
- Reserved keys are prefixed with `extra_` (e.g., `message` → `extra_message`)

### 5. Async Warnings

#### 5.1. Check Console During Pipeline

Run pipeline and watch console output.

**Expected:**
- No `RuntimeWarning: coroutine '...' was never awaited` warnings
- No async-related warnings

**Look for:**
```
❌ BAD: RuntimeWarning: coroutine 'job_daily_pipeline' was never awaited
✅ GOOD: No async warnings
```

### 6. Transparency Dashboard

#### 6.1. Check Transparency Endpoint

```bash
curl -i http://localhost:8000/api/v1/transparency/status
```

**Expected:**
- Status 200 (if endpoint exists)
- OR Status 404 (if not implemented)
- Response is valid JSON

#### 6.2. Check UI (if available)

If transparency dashboard exists in frontend:

**Expected:**
- Dashboard loads without errors
- Cards populate with data
- No console errors

## Validation Checklist

Use this checklist to track validation progress:

### Backend Startup & Pipeline (FIX-02)
- [ ] Backend starts without errors
- [ ] Scheduler initializes
- [ ] Initial pipeline runs automatically (if no today's recommendation exists)
- [ ] `/api/v1/recommendation/today` returns populated payload or structured error
- [ ] Manual pipeline trigger works

### Endpoints (FIX-01)
- [ ] `/api/v1/recommendation/today` returns 200 with correct structure
- [ ] `/api/v1/recommendation/history` returns 200 with `items` (not `recommendations`)
- [ ] `/api/v1/recommendation/history` includes `next_cursor`, `has_more`, `insights`, `download_url`
- [ ] `/api/v1/recommendation/performance` returns 200 with correct structure
- [ ] No 404 or 422 errors on any endpoint

### Frontend → Backend Proxy
- [ ] Frontend dev server starts
- [ ] Network requests to `/api/...` succeed
- [ ] Data displays in UI (tables, charts)
- [ ] No CORS or connection errors

### Logging (FIX-03)
- [ ] No `KeyError: Attempt to overwrite` errors in logs
- [ ] Reserved keys are sanitized (prefixed with `extra_`)
- [ ] Error contexts are preserved
- [ ] Logs are structured and readable

### Async Warnings
- [ ] No `RuntimeWarning: coroutine was never awaited` warnings
- [ ] Pipeline runs without async warnings

### Transparency Dashboard
- [ ] Transparency endpoint accessible (if implemented)
- [ ] UI cards populate without errors (if available)

## Troubleshooting

### Backend won't start
- Check if port 8000 is in use
- Verify dependencies: `poetry install`
- Check logs for errors

### Pipeline doesn't run automatically
- Verify `AUTO_RUN_PIPELINE_ON_START=True` in config
- Check if recommendation for today already exists
- Manually trigger pipeline via API

### Endpoints return 404/422
- Verify backend is running
- Check endpoint paths match frontend expectations
- Verify database is populated

### KeyError in logs
- Check that `sanitize_log_extra` is imported where needed
- Verify all logger calls with `extra=` use sanitization
- Check for any missed logger calls

### Frontend can't connect
- Verify backend is running on port 8000
- Check Vite proxy configuration
- Verify CORS settings

## Next Steps

After validation:

1. **If all checks pass:** Fixes are working correctly
2. **If some checks fail:** Review error messages and fix issues
3. **Document any issues:** Note any problems for follow-up fixes

## Related Documentation

- [FIX-01 Details](../CHECKLIST_VALIDATION.md#fix-01)
- [FIX-02 Details](../CHECKLIST_VALIDATION.md#fix-02)
- [FIX-03 Details](../CHECKLIST_VALIDATION.md#fix-03)
- [API Documentation](./api.md)
- [Backend README](../backend/README.md)

