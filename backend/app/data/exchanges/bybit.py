"""Bybit perpetual futures data source."""
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

_INTERVAL_MAP = {
    "1m": "1",
    "3m": "3",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "4h": "240",
    "6h": "360",
    "12h": "720",
    "1d": "D",
}

_OI_INTERVAL_MAP = {
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}


class BybitPerpetualDataSource(HTTPExchangeClient):
    base_url = "https://api.bybit.com"
    venue = "bybit_perp"

    async def fetch_candles(
        self,
        symbol: str,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> Iterable[Candle]:
        params = {
            "category": "linear",
            "symbol": symbol.upper(),
            "interval": _INTERVAL_MAP.get(interval, "1"),
            "limit": min(limit, 1000),
        }
        if start:
            params["start"] = int(start.timestamp() * 1000)
        if end:
            params["end"] = int(end.timestamp() * 1000)

        raw = await self._request("GET", "/v5/market/kline", params=params)
        data = raw.get("result", {}).get("list", [])
        candles: List[Candle] = []
        for entry in data:
            open_time = datetime.fromtimestamp(int(entry[0]) / 1000, tz=timezone.utc)
            close_time = datetime.fromtimestamp(int(entry[6]) / 1000, tz=timezone.utc)
            candles.append(
                Candle(
                    open_time=open_time,
                    close_time=close_time,
                    open=float(entry[1]),
                    high=float(entry[2]),
                    low=float(entry[3]),
                    close=float(entry[4]),
                    volume=float(entry[5]),
                    venue=self.venue,
                    symbol=symbol.upper(),
                    extras={
                        "turnover": float(entry[7]),
                    },
                )
            )
        return candles

    async def fetch_funding(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> Iterable[FundingRate]:
        params = {
            "category": "linear",
            "symbol": symbol.upper(),
            "limit": min(limit, 200),
        }
        if start:
            params["startTime"] = int(start.timestamp() * 1000)
        if end:
            params["endTime"] = int(end.timestamp() * 1000)

        raw = await self._request("GET", "/v5/market/funding/history", params=params)
        data = raw.get("result", {}).get("list", [])
        events: List[FundingRate] = []
        for item in data:
            events.append(
                FundingRate(
                    symbol=symbol.upper(),
                    venue=self.venue,
                    rate=float(item["fundingRate"]),
                    timestamp=datetime.fromtimestamp(int(item["fundingRateTimestamp"]) / 1000, tz=timezone.utc),
                    extras={},
                )
            )
        return events

    async def fetch_open_interest(
        self,
        symbol: str,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> Iterable[OpenInterest]:
        params = {
            "category": "linear",
            "symbol": symbol.upper(),
            "intervalTime": _OI_INTERVAL_MAP.get(interval, "5min"),
            "limit": min(limit, 200),
        }
        if start:
            params["startTime"] = int(start.timestamp() * 1000)
        if end:
            params["endTime"] = int(end.timestamp() * 1000)

        raw = await self._request("GET", "/v5/market/open-interest", params=params)
        data = raw.get("result", {}).get("list", [])
        interests: List[OpenInterest] = []
        for item in data:
            timestamp = datetime.fromtimestamp(int(item["timestamp"]) / 1000, tz=timezone.utc)
            interests.append(
                OpenInterest(
                    symbol=symbol.upper(),
                    venue=self.venue,
                    open_interest=float(item["openInterest"]),
                    notional=float(item.get("turnover", 0.0)) if item.get("turnover") else None,
                    timestamp=timestamp,
                    extras={},
                )
            )
        return interests

    async def fetch_liquidations(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> Iterable[LiquidationEvent]:
        params = {
            "category": "linear",
            "symbol": symbol.upper(),
            "limit": min(limit, 200),
        }
        if start:
            params["startTime"] = int(start.timestamp() * 1000)
        if end:
            params["endTime"] = int(end.timestamp() * 1000)

        raw = await self._request("GET", "/v5/market/liquidation", params=params)
        data = raw.get("result", {}).get("list", [])
        events: List[LiquidationEvent] = []
        for item in data:
            qty = float(item.get("qty", 0.0))
            price = float(item.get("price", 0.0))
            notional = qty * price if qty and price else None
            events.append(
                LiquidationEvent(
                    symbol=symbol.upper(),
                    venue=self.venue,
                    side=item.get("side", "").lower() or "unknown",
                    price=price,
                    quantity=qty,
                    notional=notional,
                    timestamp=datetime.fromtimestamp(int(item["updatedTime"]) / 1000, tz=timezone.utc),
                    extras={"value": float(item.get("value", 0.0))},
                )
            )
        return events

    async def fetch_orderbook(
        self,
        symbol: str,
        *,
        depth: int = 50,
    ) -> OrderBookDepth | None:
        params = {
            "category": "linear",
            "symbol": symbol.upper(),
            "limit": min(depth, 200),
        }
        raw = await self._request("GET", "/v5/market/orderbook", params=params)
        result = raw.get("result", {})
        timestamp = datetime.fromtimestamp(int(result.get("ts", 0)) / 1000, tz=timezone.utc)
        bids_raw = result.get("b", [])
        asks_raw = result.get("a", [])
        bids = [OrderBookLevel(price=float(price), quantity=float(qty)) for price, qty in bids_raw]
        asks = [OrderBookLevel(price=float(price), quantity=float(qty)) for price, qty in asks_raw]
        return OrderBookDepth(
            symbol=symbol.upper(),
            venue=self.venue,
            timestamp=timestamp,
            bids=bids,
            asks=asks,
        )



