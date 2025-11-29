# FE-DATA-01: Market Data Shape Alignment with Frontend Chart Expectations

## Issue Description

The `/api/v1/market/{interval}` endpoint was missing the `open` field in the data array, causing potential runtime issues in the chart component. Additionally, loading/error/degraded states needed improvement for better user experience.

## Root Cause

1. **Missing `open` field**: The backend endpoint was providing `close`, `high`, `low`, `volume` but missing `open` in the OHLC data structure
2. **Data structure mismatch**: Frontend expects complete OHLC structure matching the `MarketPoint` interface
3. **Incomplete error handling**: Processing (202) and degraded states needed better user-facing messages

## Fixes Applied

### 1. Backend - Added Missing `open` Field

**File**: `backend/app/api/v1/market.py`

Added `open` field to the data array to match frontend `MarketPoint` interface expectations:

```python
data["data"] = [
    {
        "open_time": row["open_time"].isoformat() if hasattr(row["open_time"], "isoformat") else str(row["open_time"]),
        "timestamp": row["open_time"].isoformat() if hasattr(row["open_time"], "isoformat") else str(row["open_time"]),
        "open": float(row["open"]),  # ✅ Added missing field
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "volume": float(row["volume"]),
    }
    for _, row in recent.iterrows()
]
```

### 2. Frontend - Improved Data Validation

**File**: `frontend/src/pages/Dashboard.tsx`

- Added validation to filter out invalid entries before processing
- Improved fallback logic with better comments explaining the data structure
- Enhanced empty state handling for `no_data` status
- Added better error messages for missing candle data

### 3. Frontend - Enhanced Loading/Error/Degraded States

**File**: `frontend/src/pages/Dashboard.tsx`

- Added handling for processing (202) status with user-friendly messages
- Improved empty state messages for different scenarios:
  - `no_data` status
  - Empty candle data
  - Missing recommendation data
- Added retry buttons where appropriate
- Better integration with `DegradedDataBanner` for stale data warnings

## Data Structure Alignment

### Backend Response (Now Correct)
```json
{
  "interval": "1h",
  "status": "success",
  "data": [
    {
      "open_time": "2024-01-15T12:00:00Z",
      "timestamp": "2024-01-15T12:00:00Z",
      "open": 45200.0,     // ✅ Now included
      "high": 45300.0,
      "low": 45100.0,
      "close": 45250.0,
      "volume": 1250.5
    }
  ],
  "metadata": {
    "as_of": "2024-01-15T12:00:00Z",
    "served_from_cache": false,
    "age_minutes": 5.2
  }
}
```

### Frontend Expectation (`MarketPoint` Interface)
```typescript
interface MarketPoint {
  timestamp: string
  open: number      // ✅ Now provided by backend
  high: number
  low: number
  close: number
  volume: number
  projection?: number
}
```

## Status Handling

### Backend Status Codes
- `200`: Success with fresh data
- `202`: Processing (pipeline running)
- `503`: Data stale (but available)
- `500`: Error

### Frontend Handling
- **Loading**: Shows spinner with descriptive message
- **Processing (202)**: Shows loading state with explanation and retry button
- **Error**: Shows error state with retry functionality
- **Degraded/Stale**: Shows `DegradedDataBanner` with warning and metadata
- **No Data**: Shows empty state with helpful instructions

## Acceptance Criteria

✅ **Chart loads without runtime errors**
- Added validation to filter invalid entries
- All OHLC fields now provided by backend
- Frontend has safe fallbacks for edge cases

✅ **Candles and recommendation overlays render with correct timestamps**
- Timestamps properly formatted (ISO strings)
- Data sorted chronologically
- Recommendation overlays use same timestamp format

✅ **Loading/error/degraded states surfaced with user-friendly copy**
- Processing state: "El pipeline de datos se está ejecutando..."
- No data: "No hay datos de mercado disponibles..."
- Empty candles: "No hay datos de velas disponibles..."
- Stale data: Shows `DegradedDataBanner` with age information

## Testing Recommendations

1. Test with empty market data (`status: "no_data"`)
2. Test with processing status (202 response)
3. Test with stale data (`status: "data_stale"`)
4. Test with missing recommendation data
5. Verify chart renders correctly with complete OHLC data
6. Verify timestamps align correctly between candles and recommendation overlays

