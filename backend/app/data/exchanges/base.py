"""Common dataclasses and protocols for exchange data sources."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Mapping, Protocol, Sequence


@dataclass(frozen=True, slots=True)
class Candle:
    open_time: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    venue: str
    symbol: str
    extras: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FundingRate:
    symbol: str
    venue: str
    rate: float
    timestamp: datetime
    extras: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OpenInterest:
    symbol: str
    venue: str
    open_interest: float
    notional: float | None
    timestamp: datetime
    extras: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LiquidationEvent:
    symbol: str
    venue: str
    side: str
    price: float
    quantity: float
    notional: float | None
    timestamp: datetime
    extras: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OrderBookLevel:
    price: float
    quantity: float


@dataclass(frozen=True, slots=True)
class OrderBookDepth:
    symbol: str
    venue: str
    timestamp: datetime
    bids: Sequence[OrderBookLevel]
    asks: Sequence[OrderBookLevel]

    @property
    def best_bid(self) -> OrderBookLevel | None:
        return self.bids[0] if self.bids else None

    @property
    def best_ask(self) -> OrderBookLevel | None:
        return self.asks[0] if self.asks else None

    @property
    def bid_depth(self) -> float:
        return float(sum(level.quantity for level in self.bids)) if self.bids else 0.0

    @property
    def ask_depth(self) -> float:
        return float(sum(level.quantity for level in self.asks)) if self.asks else 0.0


class ExchangeDataSource(Protocol):
    venue: str

    async def fetch_candles(
        self,
        symbol: str,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> Iterable[Candle]:
        ...

    async def fetch_funding(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> Iterable[FundingRate]:
        ...

    async def fetch_open_interest(
        self,
        symbol: str,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 500,
    ) -> Iterable[OpenInterest]:
        ...

    async def fetch_liquidations(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 500,
    ) -> Iterable[LiquidationEvent]:
        ...

    async def fetch_orderbook(
        self,
        symbol: str,
        *,
        depth: int = 50,
    ) -> OrderBookDepth | None:
        ...

