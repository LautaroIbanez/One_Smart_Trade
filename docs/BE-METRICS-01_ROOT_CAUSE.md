# BE-METRICS-01: Root Cause Analysis - FALLBACK_NO_TRADES vs NO_TRADES

## Issue Description

Performance summary was returning `FALLBACK_NO_TRADES` status despite `has_metrics=true` when only minimal metrics existed (just `total_trades=0`, `winning_trades=0`, `losing_trades=0`).

## Root Cause

When `metrics_status` was missing or `UNKNOWN` from cached results, the code incorrectly defaulted to `FALLBACK_NO_TRADES` for all zero-trade scenarios, without distinguishing between:

1. **NO_TRADES**: Minimal metrics only (just trade counts, no synthetic/fallback metrics)
2. **FALLBACK_NO_TRADES**: Fallback/synthetic metrics exist (has CAGR, Sharpe, max_drawdown, etc.)

This happened in three locations:
- `performance_service.py` line 420-431: Fallback logic after metrics calculation
- `performance_service.py` line 968-982: DB cache retrieval with missing status
- `performance.py` line 476-489: API endpoint with missing status

## Fix

### 1. Status Mapping Logic

Updated the fallback logic to check if metrics contain fallback/synthetic values vs minimal structure only:

```python
if trade_count == 0:
    # Check if metrics contain fallback/synthetic values vs minimal structure only
    has_fallback_metrics = bool(
        metrics.get("cagr") is not None
        or metrics.get("sharpe_ratio") is not None
        or metrics.get("max_drawdown") is not None
        or len(metrics) > 3  # More than just total_trades, winning_trades, losing_trades
    )
    if has_fallback_metrics:
        metrics_status = "FALLBACK_NO_TRADES"
    else:
        metrics_status = "NO_TRADES"
```

### 2. Status Meanings

- **NO_TRADES**: No trades executed, minimal metrics only (just trade counts)
- **FALLBACK_NO_TRADES**: No trades executed BUT fallback/synthetic metrics were generated (e.g., in dev mode or when metrics were previously generated)

### 3. Files Modified

1. `backend/app/services/performance_service.py`
   - Lines 420-431: Fixed fallback logic after metrics calculation
   - Lines 968-1010: Fixed DB cache retrieval logic

2. `backend/app/api/v1/performance.py`
   - Lines 476-489: Fixed API endpoint fallback logic

3. `tests/services/test_performance_service_fallback_metrics.py`
   - Added `test_no_trades_vs_fallback_no_trades_distinction()` to validate the fix

## Acceptance Criteria

✅ Root cause identified and documented in code comments  
✅ Performance summary returns PASS or an explicit, accurate reason when trades truly absent  
✅ At least one regression/unit test covering the corrected status (`test_no_trades_vs_fallback_no_trades_distinction`)

## Testing

The test validates three scenarios:
1. Minimal metrics only → `NO_TRADES`
2. Fallback metrics exist → `FALLBACK_NO_TRADES`
3. Explicit `NO_TRADES` status preserved when set

