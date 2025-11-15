"""Coinbase exchange data source."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


_GRANULARITY_MAP = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14_400,
    "6h": 21_600,
    "12h": 43_200,
    "1d": 86_400,
}


class CoinbaseDataSource(HTTPExchangeClient):
    base_url = "https://api.exchange.coinbase.com"
    venue = "coinbase"

    async def fetch_candles(
        self,
        symbol: str,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 300,
    ) -> Iterable[Candle]:
        params = {
            "granularity": _GRANULARITY_MAP.get(interval, 60),
        }
        if start:
            params["start"] = start.replace(tzinfo=timezone.utc).isoformat()
        if end:
            params["end"] = end.replace(tzinfo=timezone.utc).isoformat()

        product = symbol.replace("-", "/").upper().replace("/", "-")
        raw = await self._request("GET", f"/products/{product}/candles", params=params)
        # Coinbase returns newest first
        candles: List[Candle] = []
        for entry in sorted(raw, key=lambda e: e[0]):
            open_time = datetime.fromtimestamp(entry[0], tz=timezone.utc)
            close_time = open_time + _granularity_to_duration(params["granularity"])
            candles.append(
                Candle(
                    open_time=open_time,
                    close_time=close_time,
                    open=float(entry[3]),
                    high=float(entry[2]),
                    low=float(entry[1]),
                    close=float(entry[4]),
                    volume=float(entry[5]),
                    venue=self.venue,
                    symbol=product,
                    extras={},
                )
            )
        return candles

    async def fetch_funding(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> Iterable[FundingRate]:
        # Coinbase spot does not provide funding rates; return empty list.
        return []

    async def fetch_open_interest(
        self,
        symbol: str,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 500,
    ) -> Iterable[OpenInterest]:
        # Coinbase spot does not expose open interest; return empty list.
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
        product = symbol.replace("-", "/").upper().replace("/", "-")
        params = {"level": 2 if depth > 1 else 1}
        raw = await self._request("GET", f"/products/{product}/book", params=params)
        timestamp = datetime.now(tz=timezone.utc)
        bids = [OrderBookLevel(price=float(price), quantity=float(qty)) for price, qty, *_ in raw.get("bids", [])]
        asks = [OrderBookLevel(price=float(price), quantity=float(qty)) for price, qty, *_ in raw.get("asks", [])]
        return OrderBookDepth(symbol=product, venue=self.venue, timestamp=timestamp, bids=bids, asks=asks)


def _granularity_to_duration(seconds: int):
    return timedelta(seconds=seconds)

