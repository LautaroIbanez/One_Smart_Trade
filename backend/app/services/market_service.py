"""Market data service."""
from typing import Any

from app.data.curation import DataCuration


class MarketService:
    """Service for market data operations."""

    def __init__(self):
        self.curation = DataCuration()

    async def get_market_data(self, interval: str) -> dict[str, Any]:
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
        chart_points = [
            {
                "timestamp": row["open_time"].isoformat(),
                "price": float(row["close"]),
            }
            for _, row in df.tail(200).iterrows()
        ]
        # Calculate support/resistance from recent data (last 100 candles)
        recent = df.tail(100) if len(df) >= 100 else df
        support = float(recent["low"].min()) if not recent.empty else float(latest.get("support", 0))
        resistance = float(recent["high"].max()) if not recent.empty else float(latest.get("resistance", 0))

        # Use curated support/resistance if available, otherwise use calculated
        support = float(latest.get("support", support)) if latest.get("support", 0) > 0 else support
        resistance = float(latest.get("resistance", resistance)) if latest.get("resistance", 0) > 0 else resistance

        return {
            "interval": interval,
            "status": "success",
            "current_price": float(latest["close"]),
            "volume": float(latest["volume"]),
            "vwap": float(latest.get("vwap", latest["close"])),
            "atr": float(latest.get("atr_14", latest.get("atr", 0))),
            "volatility": float(latest.get("volatility_30", latest.get("realized_volatility", 0))),
            "support": support,
            "resistance": resistance,
            "timestamp": latest["open_time"].isoformat(),
            "data": chart_points,
        }

