"""Binance Futures (USDT-margined) data source."""
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


class BinanceFuturesUSDTDataSource(HTTPExchangeClient):
    base_url = "https://fapi.binance.com"
    venue = "binance_futures"

    async def fetch_candles(
        self,
        symbol: str,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> Iterable[Candle]:
        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": min(limit, 1500),
        }
        if start:
            params["startTime"] = int(start.timestamp() * 1000)
        if end:
            params["endTime"] = int(end.timestamp() * 1000)

        raw = await self._request("GET", "/fapi/v1/klines", params=params)
        candles: List[Candle] = []
        for entry in raw:
            open_time = datetime.fromtimestamp(entry[0] / 1000, tz=timezone.utc)
            close_time = datetime.fromtimestamp(entry[6] / 1000, tz=timezone.utc)
            extras = {
                "quote_volume": float(entry[7]),
                "trades": float(entry[8]),
                "taker_buy_base": float(entry[9]),
                "taker_buy_quote": float(entry[10]),
            }
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
                    extras=extras,
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
        params = {
            "symbol": symbol.upper(),
            "limit": min(limit, 1000),
        }
        if start:
            params["startTime"] = int(start.timestamp() * 1000)
        if end:
            params["endTime"] = int(end.timestamp() * 1000)

        raw = await self._request("GET", "/fapi/v1/fundingRate", params=params)
        funding: List[FundingRate] = []
        for item in raw:
            funding.append(
                FundingRate(
                    symbol=symbol.upper(),
                    venue=self.venue,
                    rate=float(item["fundingRate"]),
                    timestamp=datetime.fromtimestamp(item["fundingTime"] / 1000, tz=timezone.utc),
                    extras={"mark_price": float(item.get("markPrice", 0.0))},
                )
            )
        return funding

    async def fetch_open_interest(
        self,
        symbol: str,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 500,
    ) -> Iterable[OpenInterest]:
        params = {
            "symbol": symbol.upper(),
            "period": interval,
            "limit": min(limit, 500),
        }
        if start:
            params["startTime"] = int(start.timestamp() * 1000)
        if end:
            params["endTime"] = int(end.timestamp() * 1000)

        raw = await self._request("GET", "/futures/data/openInterestHist", params=params)
        interests: List[OpenInterest] = []
        for item in raw:
            timestamp = datetime.fromtimestamp(int(item["timestamp"]) / 1000, tz=timezone.utc)
            interests.append(
                OpenInterest(
                    symbol=symbol.upper(),
                    venue=self.venue,
                    open_interest=float(item["sumOpenInterest"]),
                    notional=float(item.get("sumOpenInterestValue", 0.0)) if item.get("sumOpenInterestValue") else None,
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
        limit: int = 500,
    ) -> Iterable[LiquidationEvent]:
        params = {
            "symbol": symbol.upper(),
            "limit": min(limit, 1000),
        }
        if start:
            params["startTime"] = int(start.timestamp() * 1000)
        if end:
            params["endTime"] = int(end.timestamp() * 1000)

        raw = await self._request("GET", "/fapi/v1/forceOrders", params=params)
        events: List[LiquidationEvent] = []
        for item in raw:
            price = float(item.get("price", 0.0))
            qty = float(item.get("qty", 0.0))
            notional = price * qty if price and qty else None
            events.append(
                LiquidationEvent(
                    symbol=symbol.upper(),
                    venue=self.venue,
                    side=item.get("side", "").lower() or "unknown",
                    price=price,
                    quantity=qty,
                    notional=notional,
                    timestamp=datetime.fromtimestamp(item["time"] / 1000, tz=timezone.utc),
                    extras={
                        "order_type": item.get("orderType", ""),
                    },
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
            "symbol": symbol.upper(),
            "limit": min(depth, 500),
        }
        raw = await self._request("GET", "/fapi/v1/depth", params=params)
        timestamp = datetime.fromtimestamp(raw.get("T", raw.get("lastUpdateId", 0)) / 1000, tz=timezone.utc)
        bids = [OrderBookLevel(price=float(price), quantity=float(qty)) for price, qty in raw.get("bids", [])]
        asks = [OrderBookLevel(price=float(price), quantity=float(qty)) for price, qty in raw.get("asks", [])]
        return OrderBookDepth(symbol=symbol.upper(), venue=self.venue, timestamp=timestamp, bids=bids, asks=asks)

