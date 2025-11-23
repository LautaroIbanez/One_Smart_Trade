"""Dev mode utilities for seeding demo data when live ingestion fails."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.core.config import settings
from app.core.logging import logger
from app.data.ingestion import INTERVALS
from app.data.storage import RAW_ROOT, ensure_partition_dirs, get_raw_path, write_parquet


def has_local_raw_data(venue: str = "binance", symbol: str = "BTCUSDT") -> bool:
    """
    Check if any local raw data files exist for the given venue/symbol.
    
    Args:
        venue: Trading venue (default: "binance")
        symbol: Trading symbol (default: "BTCUSDT")
        
    Returns:
        True if at least one raw parquet file exists for any interval, False otherwise
    """
    for interval in INTERVALS:
        raw_dir = get_raw_path(venue, symbol, interval).parent
        if raw_dir.exists():
            parquet_files = list(raw_dir.glob("*.parquet"))
            if parquet_files:
                return True
    return False


def seed_demo_klines(
    venue: str = "binance",
    symbol: str = "BTCUSDT",
    *,
    days: int = 90,
) -> dict[str, Any]:
    """
    Generate and persist demo klines data for all intervals.
    
    Creates realistic-looking price data with proper OHLCV structure.
    This allows dev environments to work without Binance API access.
    
    Args:
        venue: Trading venue (default: "binance")
        symbol: Trading symbol (default: "BTCUSDT")
        days: Number of days of historical data to generate (default: 90)
        
    Returns:
        Dictionary with seeding results per interval
    """
    logger.info(f"Seeding demo klines data for {venue}/{symbol} ({days} days)")
    
    results: dict[str, Any] = {}
    base_price = 45000.0  # Starting BTC price
    base_time = datetime.now(timezone.utc) - timedelta(days=days)
    
    # Interval to minutes mapping
    interval_minutes = {
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "4h": 240,
        "1d": 1440,
        "1w": 10080,
    }
    
    for interval in INTERVALS:
        try:
            interval_mins = interval_minutes.get(interval, 60)
            num_candles = (days * 1440) // interval_mins
            
            # Generate timestamps
            timestamps = pd.date_range(
                start=base_time,
                periods=num_candles,
                freq=f"{interval_mins}min",
                tz=timezone.utc
            )
            
            # Generate realistic price movement (random walk with trend)
            np.random.seed(42)  # Deterministic for reproducibility
            returns = np.random.normal(0.0001, 0.02, num_candles)  # Small drift, 2% volatility
            prices = base_price * (1 + returns).cumprod()
            
            # Generate OHLCV data
            data = []
            for i, (ts, close) in enumerate(zip(timestamps, prices)):
                # Generate realistic OHLC from close price
                volatility = abs(np.random.normal(0, 0.005))  # 0.5% intraday volatility
                high = close * (1 + volatility)
                low = close * (1 - volatility)
                
                if i == 0:
                    open_price = close
                else:
                    # Open price is close to previous close
                    open_price = prices[i-1] * (1 + np.random.normal(0, 0.001))
                
                # Ensure OHLC relationships are valid
                high = max(high, open_price, close)
                low = min(low, open_price, close)
                
                # Generate volume (higher volume on larger moves)
                price_change_pct = abs((close - open_price) / open_price) if open_price > 0 else 0
                base_volume = 1000.0
                volume = base_volume * (1 + price_change_pct * 10) * np.random.uniform(0.5, 2.0)
                
                data.append({
                    "open_time": ts,
                    "open": round(open_price, 2),
                    "high": round(high, 2),
                    "low": round(low, 2),
                    "close": round(close, 2),
                    "volume": round(volume, 2),
                    "quote_asset_volume": round(volume * close, 2),
                    "taker_buy_base": round(volume * 0.5, 2),
                    "taker_buy_quote": round(volume * close * 0.5, 2),
                    "number_of_trades": int(np.random.uniform(100, 1000)),
                    "venue": venue,
                    "symbol": symbol,
                })
            
            df = pd.DataFrame(data)
            
            # Write to parquet
            filename = f"{base_time.strftime('%Y-%m-%dT%H-%M-%S')}.parquet"
            output_path = get_raw_path(venue, symbol, interval, filename=filename)
            ensure_partition_dirs(venue, symbol, interval)
            
            meta = {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "symbol": symbol,
                "interval": interval,
                "venue": venue,
                "rows": len(df),
                "demo_data": True,  # Flag to indicate this is demo data
            }
            
            write_parquet(df, output_path, metadata=meta)
            
            results[interval] = {
                "status": "success",
                "rows": len(df),
                "path": str(output_path),
                "demo_data": True,
            }
            
            logger.info(f"Seeded {len(df)} demo candles for {interval}")
            
        except Exception as exc:
            logger.error(f"Failed to seed demo data for {interval}: {exc}", exc_info=True)
            results[interval] = {
                "status": "error",
                "error": str(exc),
            }
    
    return results

