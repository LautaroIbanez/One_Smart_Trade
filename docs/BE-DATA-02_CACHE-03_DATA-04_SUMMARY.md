# BE-DATA-02, BE-CACHE-03, FE-DATA-04: Market Data Freshness and Cache Invalidation Fixes

## Issues Identified

### BE-DATA-02: Ingestion Job Not Triggering Curation
- **Problem**: The `job_ingest_all` scheduler (runs every 15 minutes) only ingested raw data but did not trigger curation, leaving curated parquet files stale
- **Impact**: Market endpoint served old candles (e.g., from 11/11) because curated parquet wasn't updated
- **Root Cause**: Curation was only triggered in the daily pipeline, not in the regular 15-minute ingestion job

### BE-CACHE-03: Cache Invalidation Not Working Properly
- **Problem**: Cache version relied on metadata that might not update when new data arrives
- **Impact**: Frontend continued receiving stale cached responses even after new candles were available
- **Root Cause**: Cache invalidation wasn't triggered after curation, and age_minutes wasn't logged for observability

### FE-DATA-04: Chart Refresh Coupled to Recommendation Timestamp
- **Problem**: Market data query key included `recommendationTimestamp`, so if recommendation didn't change, chart wouldn't refresh even with new candles
- **Impact**: Chart remained frozen showing old data until recommendation changed
- **Root Cause**: Query key dependency on recommendation timestamp prevented independent refresh

## Fixes Applied

### BE-DATA-02: Trigger Curation After Ingestion

**File**: `backend/app/main.py` - `job_ingest_all()`

**Changes**:
1. Added curation pipeline execution after successful ingestion
2. Curates all intervals that had successful ingestion
3. Logs curation results for observability
4. Invalidates market data cache after curation completes

```python
# After ingestion completes successfully:
# 1. Trigger curation for all successfully ingested intervals
# 2. Invalidate market_data cache to ensure fresh responses
# 3. Log results for observability
```

**Result**: Curated parquet files are now updated every 15 minutes along with raw data ingestion.

### BE-CACHE-03: Improve Cache Invalidation and Observability

**File**: `backend/app/api/v1/market.py`

**Changes**:
1. Added age_minutes logging for observability
2. Added warning logs when data approaches stale threshold
3. Cache version already includes `latest_open_time` from metadata, so it automatically invalidates when curation updates metadata

**File**: `backend/app/main.py` - `job_ingest_all()`

**Changes**:
1. Added cache invalidation after curation completes using `clear_cache("market_data")`
2. This ensures next request picks up fresh metadata with updated `latest_open_time`

**Result**: Cache automatically invalidates when new data arrives, and logs provide visibility into data freshness.

### FE-DATA-04: Decouple Market Query from Recommendation

**File**: `frontend/src/api/hooks.ts` - `useMarketData()`

**Changes**:
1. Removed `recommendationTimestamp` from query key
2. Query key now only includes `['market', interval, window]`
3. Reduced `staleTime` from 5 minutes to 1 minute for faster refresh
4. Added aggressive polling (30s) when `status === 'data_stale' || 'processing'`
5. Default polling every 60s to catch new candles independently
6. Enabled `refetchOnWindowFocus` and `refetchOnReconnect`

**File**: `frontend/src/pages/Dashboard.tsx`

**Changes**:
1. Removed `recommendationTimestamp` dependency from market query call
2. Added banner showing age information when data is > 30 minutes old
3. Improved empty state messages for different scenarios (no_data, empty candles)

**Result**: Chart refreshes independently every 60s (or 30s when stale) regardless of recommendation changes.

## Acceptance Criteria Status

### BE-DATA-02 ✅
- ✅ Curation now triggered after every ingestion job execution
- ✅ Curated parquet files updated with `latest_open_time` in metadata
- ✅ Logs show ingestion and curation completion with row counts

### BE-CACHE-03 ✅
- ✅ Cache automatically invalidates when `latest_open_time` changes (via cache_version in key)
- ✅ Explicit cache invalidation after curation completes
- ✅ `age_minutes` logged for observability
- ✅ Warning logs when data approaches stale threshold

### FE-DATA-04 ✅
- ✅ Query key no longer includes recommendation timestamp
- ✅ Independent polling every 60s (or 30s when stale)
- ✅ Banner shown when `status === 'data_stale'`
- ✅ Manual refresh available via retry buttons

## Testing Recommendations

1. **Verify Ingestion + Curation Pipeline**:
   - Check scheduler logs show both ingestion and curation completing every 15 minutes
   - Verify `data/curated/<venue>/<symbol>/1h/latest.parquet` has recent `latest_open_time`
   - Verify `.meta.json` includes `latest_open_time` and `generated_at`

2. **Verify Cache Invalidation**:
   - Check logs show cache invalidation after curation
   - Verify `/api/v1/market/1h` returns updated `metadata.as_of` after new candles
   - Verify `age_minutes` appears in logs

3. **Verify Frontend Refresh**:
   - Verify chart updates within 1 minute of new candles arriving
   - Verify chart refreshes even when recommendation stays the same (e.g., HOLD)
   - Verify stale data banner appears when appropriate
   - Verify manual refresh buttons work

## Monitoring

- **Backend Logs**: Look for "Ingestion and curation completed" messages with row counts
- **Backend Logs**: Look for "Invalidated N market_data cache entries after curation"
- **Backend Logs**: Look for "Market data served for {interval}" with age_minutes
- **Frontend**: Chart should update independently every 60s (check Network tab)
- **Frontend**: Stale banners should appear when `status === 'data_stale'`


