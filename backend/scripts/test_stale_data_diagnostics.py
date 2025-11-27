"""Test script to verify stale data diagnostics in signal_data_provider and daily_strategy_adapter."""
import asyncio
import os
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from pathlib import Path
from app.core.config import settings
from app.data.signal_data_provider import SignalDataProvider
from app.data.curation import DataCuration
from app.backtesting.daily_strategy_adapter import DailyStrategyAdapter
from app.quant.signal_engine import DailySignalEngine


async def test_stale_data_diagnostics():
    """Test that stale data is properly detected and reported."""
    print("=" * 80)
    print("Testing stale data diagnostics")
    print("=" * 80)
    
    # Enable dev mode for this test
    original_dev_mode = os.environ.get("DEV_MODE", "False")
    os.environ["DEV_MODE"] = "True"
    
    try:
        # Create a curated dataset truncated to 2024-11-11
        print("\n1. Creating truncated dataset (up to 2024-11-11)...")
        
        # Create test data directory structure
        from app.data.storage import CURATED_ROOT, get_curated_path
        
        venue = "binance"
        symbol = "BTCUSDT"
        interval_1h = "1h"
        interval_1d = "1d"
        
        # Create directories
        curated_1h_path = get_curated_path(venue, symbol, interval_1h)
        curated_1d_path = get_curated_path(venue, symbol, interval_1d)
        curated_1h_path.parent.mkdir(parents=True, exist_ok=True)
        curated_1d_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Generate data up to 2024-11-11
        cutoff_date = pd.Timestamp("2024-11-11", tz="UTC")
        start_date = cutoff_date - timedelta(days=30)
        
        # Generate hourly data
        dates_1h = pd.date_range(start_date, cutoff_date, freq="1h", tz="UTC")
        np.random.seed(42)
        base_price = 50000.0
        prices_1h = base_price + np.cumsum(np.random.randn(len(dates_1h)) * 100)
        
        df_1h = pd.DataFrame({
            "open_time": dates_1h,
            "open": prices_1h + np.random.uniform(-50, 50, len(dates_1h)),
            "high": prices_1h + np.abs(np.random.uniform(50, 150, len(dates_1h))),
            "low": prices_1h - np.abs(np.random.uniform(50, 150, len(dates_1h))),
            "close": prices_1h,
            "volume": np.random.uniform(100, 1000, len(dates_1h)),
        })
        
        # Generate daily data
        dates_1d = pd.date_range(start_date, cutoff_date, freq="1d", tz="UTC")
        prices_1d = base_price + np.cumsum(np.random.randn(len(dates_1d)) * 500)
        
        df_1d = pd.DataFrame({
            "open_time": dates_1d,
            "open": prices_1d + np.random.uniform(-200, 200, len(dates_1d)),
            "high": prices_1d + np.abs(np.random.uniform(200, 500, len(dates_1d))),
            "low": prices_1d - np.abs(np.random.uniform(200, 500, len(dates_1d))),
            "close": prices_1d,
            "volume": np.random.uniform(1000, 5000, len(dates_1d)),
        })
        
        # Save to parquet
        df_1h.to_parquet(curated_1h_path, index=False)
        df_1d.to_parquet(curated_1d_path, index=False)
        
        print(f"   Created {len(df_1h)} hourly records (latest: {df_1h['open_time'].max()})")
        print(f"   Created {len(df_1d)} daily records (latest: {df_1d['open_time'].max()})")
        
        # Test SignalDataProvider
        print("\n2. Testing SignalDataProvider with stale data...")
        provider = SignalDataProvider(venue=venue, symbol=symbol)
        
        # Get validated inputs (should detect stale data in dev mode)
        inputs = provider.get_validated_inputs(validate_freshness=True, validate_gaps=False)
        
        # Check metadata
        metadata = inputs.metadata
        print(f"\n   Metadata from provider:")
        print(f"   - Status: {metadata.get('status') if metadata else 'None'}")
        print(f"   - Dev mode: {metadata.get('dev_mode') if metadata else 'None'}")
        print(f"   - Used legacy fallback: {metadata.get('used_legacy_fallback') if metadata else 'None'}")
        
        if metadata and "intervals" in metadata:
            for interval, interval_data in metadata["intervals"].items():
                print(f"\n   Interval {interval}:")
                print(f"     - Latest timestamp: {interval_data.get('latest_timestamp')}")
                print(f"     - Stale minutes: {interval_data.get('stale_minutes')}")
                print(f"     - Status: {interval_data.get('status')}")
        
        # Verify latest_timestamp is around 2024-11-11
        if metadata and "intervals" in metadata:
            latest_1d = metadata["intervals"].get("1d", {}).get("latest_timestamp")
            if latest_1d:
                latest_dt = pd.to_datetime(latest_1d)
                expected_date = pd.Timestamp("2024-11-11", tz="UTC")
                if latest_dt.date() == expected_date.date():
                    print(f"\n   ✓ PASS: Latest timestamp is {latest_dt.date()} (expected 2024-11-11)")
                else:
                    print(f"\n   ✗ FAIL: Latest timestamp is {latest_dt.date()} (expected 2024-11-11)")
        
        # Check if stale flag is set
        if metadata and metadata.get("status") == "stale_or_missing":
            print(f"\n   ✓ PASS: Status is 'stale_or_missing'")
        elif metadata and metadata.get("intervals", {}).get("1d", {}).get("status") == "stale":
            print(f"\n   ✓ PASS: Interval status is 'stale'")
        else:
            print(f"\n   ⚠ WARNING: Stale flag not set (may be OK if data is within threshold)")
        
        # Test DailyStrategyAdapter
        print("\n3. Testing DailyStrategyAdapter with stale data...")
        
        signal_engine = DailySignalEngine()
        adapter = DailyStrategyAdapter(
            signal_engine=signal_engine,
            df_1h=inputs.df_1h,
            df_1d=inputs.df_1d,
            symbol=symbol,
            data_metadata=inputs.metadata,
        )
        
        # Create a context for a date after the cutoff (should trigger stale_data)
        test_date = cutoff_date + timedelta(days=1)
        context = {
            "bar": pd.Series({
                "open": 50000.0,
                "high": 51000.0,
                "low": 49000.0,
                "close": 50500.0,
                "volume": 1000.0,
            }, name=test_date),
            "equity": 10000.0,
            "drawdown": 0.0,
            "position": None,
            "open_trades": 0,
        }
        
        # Generate signal
        signal = adapter.on_bar(context)
        
        print(f"\n   Signal result:")
        print(f"   - Action: {signal.get('action')}")
        print(f"   - Reason: {signal.get('reason')}")
        print(f"   - Data status: {signal.get('data_status')}")
        
        # Verify HOLD with stale_data reason
        if signal.get("action") == "hold" and signal.get("reason") == "stale_data":
            print(f"\n   ✓ PASS: Strategy correctly returns HOLD with reason=stale_data")
        else:
            print(f"\n   ✗ FAIL: Expected action=hold, reason=stale_data, got action={signal.get('action')}, reason={signal.get('reason')}")
        
        # Test with a date before cutoff (should work normally)
        print("\n4. Testing with date before cutoff (should work normally)...")
        test_date_before = cutoff_date - timedelta(days=1)
        context_before = {
            "bar": pd.Series({
                "open": 50000.0,
                "high": 51000.0,
                "low": 49000.0,
                "close": 50500.0,
                "volume": 1000.0,
            }, name=test_date_before),
            "equity": 10000.0,
            "drawdown": 0.0,
            "position": None,
            "open_trades": 0,
        }
        
        signal_before = adapter.on_bar(context_before)
        print(f"   Signal result: action={signal_before.get('action')}, reason={signal_before.get('reason', 'none')}")
        
        if signal_before.get("action") != "hold" or signal_before.get("reason") != "stale_data":
            print(f"   ✓ PASS: Strategy works normally with data before cutoff")
        else:
            print(f"   ⚠ WARNING: Strategy returned stale_data even before cutoff")
        
        print("\n" + "=" * 80)
        print("Test completed")
        print("=" * 80)
        
    finally:
        # Restore original dev mode setting
        if original_dev_mode:
            os.environ["DEV_MODE"] = original_dev_mode
        else:
            os.environ.pop("DEV_MODE", None)


if __name__ == "__main__":
    asyncio.run(test_stale_data_diagnostics())

