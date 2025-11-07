from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

import pandas as pd

from .binance_client import BinanceClient
from .storage import RAW_ROOT, write_parquet

INTERVALS: tuple[str, ...] = ("15m", "30m", "1h", "4h", "1d", "1w")


class DataIngestion:
    """Pipeline to download Binance klines and persist them as parquet."""

    def __init__(self, client: BinanceClient | None = None) -> None:
        self.client = client or BinanceClient()

    async def ingest_all_timeframes(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for interval in INTERVALS:
            try:
                result = await self.ingest_timeframe(interval)
            except Exception as exc:  # pragma: no cover - bubbled to caller
                result = {
                    "status": "error",
                    "interval": interval,
                    "rows": 0,
                    "error": str(exc),
                }
            results.append(result)
        return results

    async def ingest_timeframe(
        self,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
        *,
        symbol: str = "BTCUSDT",
        limit: int = 1000,
    ) -> dict[str, Any]:
        raw_klines, meta = await self.client.get_klines(symbol, interval, start, end, limit)
        if not raw_klines:
            return {
                "status": "empty",
                "interval": interval,
                "rows": 0,
                "meta": meta,
            }

        df = self._klines_to_dataframe(raw_klines)
        filename = meta["fetched_at"].replace(":", "-")
        output = RAW_ROOT / interval / f"{filename}.parquet"
        output.parent.mkdir(parents=True, exist_ok=True)
        write_parquet(df, output, metadata=meta | {"rows": len(df)})
        return {
            "status": "success",
            "interval": interval,
            "rows": len(df),
            "meta": meta,
            "path": str(output),
        }

    def _klines_to_dataframe(self, klines: Iterable[Iterable[Any]]) -> pd.DataFrame:
        columns = [
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_asset_volume",
            "number_of_trades",
            "taker_buy_base",
            "taker_buy_quote",
            "ignore",
        ]
        df = pd.DataFrame(klines, columns=columns)
        numeric = ["open", "high", "low", "close", "volume", "quote_asset_volume", "taker_buy_base", "taker_buy_quote"]
        for col in numeric:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
        df = df.sort_values("open_time").reset_index(drop=True)
        df.dropna(subset=["open", "high", "low", "close"], inplace=True)
        return df