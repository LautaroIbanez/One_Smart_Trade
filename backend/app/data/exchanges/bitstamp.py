"""Bitstamp exchange data source."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List

from app.data.exchanges.base import (
    Candle,
    FundingRate,
    LiquidationEvent,
    OpenInterest,
    OrderBookDepth,
    OrderBookLevel,
)
from app.data.exchanges.http import HTTPExchangeClient


_STEP_MAP = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14_400,
    "1d": 86_400,
}


class BitstampDataSource(HTTPExchangeClient):
    base_url = "https://www.bitstamp.net/api"
    venue = "bitstamp"

    async def fetch_candles(
        self,
        symbol: str,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> Iterable[Candle]:
        market = symbol.lower().replace("/", "")
        params = {
            "step": _STEP_MAP.get(interval, 60),
            "limit": min(limit, 1000),
        }
        if start:
            params["start"] = int(start.replace(tzinfo=timezone.utc).timestamp())
        if end:
            params["end"] = int(end.replace(tzinfo=timezone.utc).timestamp())

        raw = await self._request("GET", f"/v2/ohlc/{market}/", params=params)
        payload = raw.get("data", {}).get("ohlc", [])
        candles: List[Candle] = []
        for item in payload:
            open_time = datetime.fromtimestamp(int(item["timestamp"]), tz=timezone.utc)
            close_time = open_time + _step_to_duration(params["step"])
            candles.append(
                Candle(
                    open_time=open_time,
                    close_time=close_time,
                    open=float(item["open"]),
                    high=float(item["high"]),
                    low=float(item["low"]),
                    close=float(item["close"]),
                    volume=float(item["volume"]),
                    venue=self.venue,
                    symbol=symbol.upper(),
                    extras={},
                )
            )
        candles.sort(key=lambda c: c.open_time)
        return candles

    async def fetch_funding(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> Iterable[FundingRate]:
        # Bitstamp spot does not offer funding rates; return empty list.
        return []

    async def fetch_open_interest(
        self,
        symbol: str,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 500,
    ) -> Iterable[OpenInterest]:
        # Bitstamp spot has no open interest data; return empty list.
        return []

    async def fetch_liquidations(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 500,
    ) -> Iterable[LiquidationEvent]:
        return []

    async def fetch_orderbook(
        self,
        symbol: str,
        *,
        depth: int = 50,
    ) -> OrderBookDepth | None:
        market = symbol.lower().replace("/", "")
        params = {"limit": min(depth, 100)}
        raw = await self._request("GET", f"/v2/order_book/{market}/", params=params)
        timestamp = datetime.fromtimestamp(int(raw.get("timestamp", 0)), tz=timezone.utc)
        bids = [OrderBookLevel(price=float(price), quantity=float(quantity)) for price, quantity in raw.get("bids", [])]
        asks = [OrderBookLevel(price=float(price), quantity=float(quantity)) for price, quantity in raw.get("asks", [])]
        return OrderBookDepth(symbol=symbol.upper(), venue=self.venue, timestamp=timestamp, bids=bids, asks=asks)


def _step_to_duration(seconds: int):
    from datetime import timedelta

    return timedelta(seconds=seconds)

