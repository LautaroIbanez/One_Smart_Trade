"""Coordinate multi-venue ingestion with normalised candle output."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from app.data.exchanges.base import Candle, ExchangeDataSource
from app.data.storage import RAW_ROOT, ensure_partition_dirs, get_raw_path, write_parquet


@dataclass(slots=True)
class MultiVenueIngestion:
    sources: Iterable[ExchangeDataSource]
    writer: Any = field(default=write_parquet)

    async def ingest_interval(
        self,
        symbol: str,
        interval: str,
        start=None,
        end=None,
    ) -> dict[str, Any]:
        staging: list[dict[str, Any]] = []
        for source in self.sources:
            candles = await source.fetch_candles(symbol, interval, start, end)
            frame = self._to_dataframe(candles)
            depth = await source.fetch_orderbook(symbol)
            if depth and not frame.empty:
                best_bid = depth.best_bid
                best_ask = depth.best_ask
                frame["best_bid_price"] = best_bid.price if best_bid else None
                frame["best_ask_price"] = best_ask.price if best_ask else None
                frame["best_bid_qty"] = best_bid.quantity if best_bid else None
                frame["best_ask_qty"] = best_ask.quantity if best_ask else None
                frame["bid_depth"] = depth.bid_depth
                frame["ask_depth"] = depth.ask_depth
                frame["orderbook_timestamp"] = depth.timestamp
            staging.append({"source": source, "frame": frame})

        self._apply_relative_volume(staging)

        results: list[dict[str, Any]] = []
        for item in staging:
            source = item["source"]
            frame = item["frame"]
            if frame.empty:
                results.append({"venue": source.venue, "rows": 0, "path": None, "status": "no_data"})
                continue
            path = get_raw_path(source.venue, symbol, interval, filename=f"{symbol}.parquet")
            ensure_partition_dirs(source.venue, symbol, interval)
            write_result = self.writer(
                frame,
                path,
                metadata={
                    "venue": source.venue,
                    "interval": interval,
                    "symbol": symbol,
                    "rows": len(frame),
                },
            )
            results.append(
                {
                    "venue": source.venue,
                    "rows": len(frame),
                    "path": str(path),
                    "status": "stored",
                    "checksum": write_result.get("checksum"),
                }
            )
        return {
            "status": "success",
            "interval": interval,
            "symbol": symbol,
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
            "venues": results,
        }

    def _to_dataframe(self, candles: Iterable[Candle]) -> pd.DataFrame:
        records: list[dict[str, Any]] = []
        for candle in candles:
            extras = dict(candle.extras or {})
            records.append(
                {
                    "open_time": candle.open_time,
                    "close_time": candle.close_time,
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                    "venue": candle.venue,
                    "symbol": candle.symbol,
                    **extras,
                }
            )
        if not records:
            columns = [
                "open_time",
                "close_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "venue",
                "symbol",
            ]
            return pd.DataFrame(columns=columns)
        frame = pd.DataFrame.from_records(records)
        frame.sort_values("open_time", inplace=True)
        frame.reset_index(drop=True, inplace=True)
        return frame

    def _apply_relative_volume(self, staging: list[dict[str, Any]]) -> None:
        series: list[pd.DataFrame] = []
        for item in staging:
            frame = item["frame"]
            if frame.empty:
                continue
            series.append(frame[["open_time", "volume"]])
        if not series:
            return
        totals = pd.concat(series, ignore_index=True).groupby("open_time", as_index=False)["volume"].sum()
        totals.rename(columns={"volume": "total_volume"}, inplace=True)
        for item in staging:
            frame = item["frame"]
            if frame.empty:
                continue
            merged = frame.merge(totals, on="open_time", how="left")
            merged["relative_volume"] = merged["volume"] / merged["total_volume"]
            merged.drop(columns=["total_volume"], inplace=True)
            item["frame"] = merged

