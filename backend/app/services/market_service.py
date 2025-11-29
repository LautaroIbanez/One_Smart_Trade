"""Market data service."""
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from app.core.config import settings
from app.data.curation import DataCuration


class MarketService:
    """Service for market data operations."""

    def __init__(self):
        self.curation = DataCuration()

    async def get_market_data(self, interval: str, window: int = 200) -> dict[str, Any]:
        """Get market data for interval with chart-ready data."""
        try:
            df = self.curation.get_latest_curated(interval)
        except FileNotFoundError:
            df = None

        if df is None or df.empty:
            return {
                "interval": interval,
                "data": [],
                "status": "no_data",
                "current_price": 0.0,
                "support": 0.0,
                "resistance": 0.0,
            }

        latest = df.iloc[-1]
        
        # Get metadata to check freshness
        metadata = self.curation.get_curated_metadata(interval)
        latest_open_time = None
        data_stale = False
        age_minutes = None
        
        # Determine latest timestamp from metadata or dataframe
        if metadata and "latest_open_time" in metadata:
            latest_open_time_str = metadata["latest_open_time"]
            try:
                latest_open_time = datetime.fromisoformat(latest_open_time_str.replace("Z", "+00:00"))
                if latest_open_time.tzinfo is None:
                    latest_open_time = latest_open_time.replace(tzinfo=timezone.utc)
            except (ValueError, AttributeError):
                # Fallback to dataframe max
                latest_ts = pd.to_datetime(df["open_time"].max())
                if hasattr(latest_ts, 'to_pydatetime'):
                    latest_open_time = latest_ts.to_pydatetime()
                else:
                    latest_open_time = latest_ts
                if latest_open_time.tzinfo is None:
                    latest_open_time = latest_open_time.replace(tzinfo=timezone.utc)
        else:
            # Fallback to dataframe max
            latest_ts = pd.to_datetime(df["open_time"].max())
            if hasattr(latest_ts, 'to_pydatetime'):
                latest_open_time = latest_ts.to_pydatetime()
            else:
                latest_open_time = latest_ts
            if latest_open_time.tzinfo is None:
                latest_open_time = latest_open_time.replace(tzinfo=timezone.utc)
        
        # Validate freshness
        if latest_open_time:
            now = datetime.now(timezone.utc)
            age_minutes = (now - latest_open_time).total_seconds() / 60.0
            
            # Get threshold for this interval
            threshold_minutes = self.curation._get_freshness_threshold_minutes(interval)
            
            # Check if data is stale (unless in dev mode)
            dev_mode = settings.is_dev_mode()
            if not dev_mode and age_minutes > threshold_minutes:
                data_stale = True
        
        # Use configurable window (default 200, but can be overridden)
        chart_points = [
            {
                "timestamp": row["open_time"].isoformat(),
                "price": float(row["close"]),
            }
            for _, row in df.tail(window).iterrows()
        ]
        # Calculate support/resistance from recent data (last 100 candles)
        recent = df.tail(100) if len(df) >= 100 else df
        support = float(recent["low"].min()) if not recent.empty else float(latest.get("support", 0))
        resistance = float(recent["high"].max()) if not recent.empty else float(latest.get("resistance", 0))

        # Use curated support/resistance if available, otherwise use calculated
        support = float(latest.get("support", support)) if latest.get("support", 0) > 0 else support
        resistance = float(latest.get("resistance", resistance)) if latest.get("resistance", 0) > 0 else resistance

        result = {
            "interval": interval,
            "status": "data_stale" if data_stale else "success",
            "current_price": float(latest["close"]),
            "volume": float(latest["volume"]),
            "vwap": float(latest.get("vwap", latest["close"])),
            "atr": float(latest.get("atr_14", latest.get("atr", 0))),
            "volatility": float(latest.get("volatility_30", latest.get("realized_volatility", 0))),
            "support": support,
            "resistance": resistance,
            "timestamp": latest["open_time"].isoformat(),
            "data": chart_points,
            "metadata": {
                "latest_timestamp": latest_open_time.isoformat() if latest_open_time else None,
                "age_minutes": round(age_minutes, 2) if age_minutes is not None else None,
                "source": "curated_parquet",
                "window": window,
                # Include as_of timestamp matching parquet metadata
                "as_of": metadata.get("latest_open_time") if metadata else None,
                "generated_at": metadata.get("generated_at") if metadata else None,
            },
        }
        
        if data_stale:
            result["reason"] = f"Data is stale: {age_minutes:.1f} minutes old (threshold: {threshold_minutes} minutes)"
        
        return result

