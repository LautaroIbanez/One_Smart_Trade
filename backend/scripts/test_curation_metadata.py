"""Test script to verify curation metadata includes latest_open_time and DataFreshnessError behavior."""
import asyncio
import os
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from pathlib import Path
from app.data.curation import DataCuration
from app.data.ingestion import DataIngestion
from app.core.exceptions import DataFreshnessError
from app.core.config import settings


async def test_curation_metadata():
    """Test that curate_interval includes latest_open_time in metadata and DataFreshnessError behavior."""
    print("=" * 80)
    print("Testing curation metadata and DataFreshnessError")
    print("=" * 80)
    
    # Save original DEV_MODE setting
    original_dev_mode = os.environ.get("DEV_MODE", "False")
    
    try:
        # Test 1: Create data, curate it, and verify metadata includes latest_open_time
        print("\n1. Testing metadata includes latest_open_time after curation...")
        
        from app.data.storage import get_curated_path, get_raw_path, ensure_partition_dirs
        
        venue = "binance"
        symbol = "BTCUSDT"
        interval = "1d"
        
        # Create test raw data
        curated_path = get_curated_path(venue, symbol, interval)
        raw_path = get_raw_path(venue, symbol, interval)
        ensure_partition_dirs(venue, symbol, interval)
        
        # Delete existing curated file if it exists
        if curated_path.exists():
            curated_path.unlink()
            meta_path = curated_path.with_suffix(".meta.json")
            if meta_path.exists():
                meta_path.unlink()
            print(f"   Deleted existing curated file: {curated_path}")
        
        # Create synthetic raw data
        dates = pd.date_range("2024-01-01", "2024-11-10", freq="1d", tz="UTC")
        np.random.seed(42)
        base_price = 50000.0
        prices = base_price + np.cumsum(np.random.randn(len(dates)) * 100)
        
        df_raw = pd.DataFrame({
            "open_time": dates,
            "open": prices + np.random.uniform(-200, 200, len(dates)),
            "high": prices + np.abs(np.random.uniform(200, 500, len(dates))),
            "low": prices - np.abs(np.random.uniform(200, 500, len(dates))),
            "close": prices,
            "volume": np.random.uniform(1000, 5000, len(dates)),
        })
        
        # Write raw data
        raw_file = raw_path.parent / "2024-11-10.parquet"
        df_raw.to_parquet(raw_file, index=False)
        print(f"   Created raw data file: {raw_file} ({len(df_raw)} rows)")
        
        # Curate the data
        curation = DataCuration()
        result = curation.curate_interval(interval, venue=venue, symbol=symbol)
        
        print(f"\n   Curation result: {result.get('status')}")
        print(f"   Rows curated: {result.get('rows')}")
        
        # Check metadata
        metadata = curation.get_curated_metadata(interval, venue=venue, symbol=symbol)
        
        if metadata:
            print(f"\n   Metadata keys: {list(metadata.keys())}")
            latest_open_time = metadata.get("latest_open_time")
            
            if latest_open_time:
                print(f"   ✓ PASS: Metadata includes latest_open_time: {latest_open_time}")
                
                # Verify it matches the actual latest timestamp
                df_curated = curation.get_latest_curated(interval, venue=venue, symbol=symbol)
                actual_latest = df_curated["open_time"].max()
                latest_dt = pd.to_datetime(latest_open_time)
                
                if pd.to_datetime(actual_latest).date() == latest_dt.date():
                    print(f"   ✓ PASS: latest_open_time matches actual data ({actual_latest.date()})")
                else:
                    print(f"   ✗ FAIL: latest_open_time mismatch - metadata: {latest_dt.date()}, actual: {actual_latest.date()}")
            else:
                print(f"   ✗ FAIL: Metadata does not include latest_open_time")
        else:
            print(f"   ✗ FAIL: Could not read metadata")
        
        # Test 2: Test DataFreshnessError when not in DEV_MODE
        print("\n2. Testing DataFreshnessError when not in DEV_MODE...")
        
        # Disable DEV_MODE
        os.environ["DEV_MODE"] = "False"
        
        try:
            # This should raise DataFreshnessError since data is from 2024-11-10 (old)
            curation.validate_data_freshness(
                interval,
                venue=venue,
                symbol=symbol,
                skip_in_dev=False,  # Don't skip validation
            )
            print(f"   ✗ FAIL: Expected DataFreshnessError but validation passed")
        except DataFreshnessError as exc:
            print(f"   ✓ PASS: DataFreshnessError raised as expected")
            print(f"     - Interval: {exc.interval}")
            print(f"     - Latest timestamp: {exc.latest_timestamp}")
            print(f"     - Threshold minutes: {exc.threshold_minutes}")
        except Exception as exc:
            print(f"   ✗ FAIL: Unexpected exception: {type(exc).__name__}: {exc}")
        
        # Test 3: Verify that validation is skipped in DEV_MODE
        print("\n3. Testing validation is skipped in DEV_MODE...")
        
        # Enable DEV_MODE
        os.environ["DEV_MODE"] = "True"
        
        try:
            # This should not raise an error in DEV_MODE
            curation.validate_data_freshness(
                interval,
                venue=venue,
                symbol=symbol,
                skip_in_dev=True,
            )
            print(f"   ✓ PASS: Validation skipped in DEV_MODE (no exception raised)")
        except DataFreshnessError:
            print(f"   ✗ FAIL: DataFreshnessError raised even in DEV_MODE")
        except Exception as exc:
            print(f"   ✗ FAIL: Unexpected exception: {type(exc).__name__}: {exc}")
        
        # Test 4: Verify API endpoint can read latest_open_time
        print("\n4. Testing API endpoint can read latest_open_time...")
        
        from app.api.v1.operational import get_data_status
        
        # Mock the request context
        status_result = await get_data_status(interval=interval, symbol=symbol, venue=venue)
        
        print(f"   Status result: {status_result.get('status')}")
        if status_result.get("latest_open_time"):
            print(f"   ✓ PASS: API endpoint returns latest_open_time: {status_result.get('latest_open_time')}")
            print(f"   Latest date: {status_result.get('latest_open_time_date')}")
            print(f"   Age (days): {status_result.get('age_days')}")
            print(f"   Has recent data: {status_result.get('has_recent_data')}")
        else:
            print(f"   ✗ FAIL: API endpoint does not return latest_open_time")
        
        print("\n" + "=" * 80)
        print("Test completed")
        print("=" * 80)
        
    finally:
        # Restore original DEV_MODE setting
        if original_dev_mode:
            os.environ["DEV_MODE"] = original_dev_mode
        else:
            os.environ.pop("DEV_MODE", None)


if __name__ == "__main__":
    asyncio.run(test_curation_metadata())

