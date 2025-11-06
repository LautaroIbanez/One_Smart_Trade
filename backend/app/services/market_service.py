"""Market data service."""
from typing import Dict, Any
from app.data.curation import DataCuration


class MarketService:
    """Service for market data operations."""

    def __init__(self):
        self.curation = DataCuration()

    async def get_market_data(self, interval: str) -> Dict[str, Any]:
        """Get market data for interval."""
        df = self.curation.get_latest_curated(interval)
        if df is None or df.empty:
            return {"interval": interval, "data": [], "status": "no_data"}

        latest = df.iloc[-1]
        return {
            "interval": interval,
            "status": "success",
            "current_price": float(latest["close"]),
            "volume": float(latest["volume"]),
            "vwap": float(latest.get("vwap", latest["close"])),
            "atr": float(latest.get("atr", 0)),
            "volatility": float(latest.get("realized_volatility", 0)),
            "support": float(latest.get("support", 0)),
            "resistance": float(latest.get("resistance", 0)),
            "timestamp": latest["open_time"].isoformat(),
        }

