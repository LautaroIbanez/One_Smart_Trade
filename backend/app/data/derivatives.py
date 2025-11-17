"""Derivatives and microstructure data collection utilities."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

import pandas as pd

from app.data.exchanges.base import (
    ExchangeDataSource,
    FundingRate,
    LiquidationEvent,
    OpenInterest,
    OrderBookDepth,
)


@dataclass(slots=True)
class DerivativesDataCollector:
    """Collect funding, open interest, liquidations, and order book depth across venues."""

    sources: Iterable[ExchangeDataSource]

    async def funding_rates(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> pd.DataFrame:
        records = []
        for source in self.sources:
            events = await source.fetch_funding(symbol, start, end, limit=limit)
            _append_records(records, events)
        return _funding_dataframe(records)

    async def open_interest(
        self,
        symbol: str,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> pd.DataFrame:
        records = []
        for source in self.sources:
            events = await source.fetch_open_interest(symbol, interval, start, end, limit=limit)
            _append_records(records, events)
        return _open_interest_dataframe(records)

    async def liquidations(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> pd.DataFrame:
        records = []
        for source in self.sources:
            events = await source.fetch_liquidations(symbol, start, end, limit=limit)
            _append_records(records, events)
        return _liquidation_dataframe(records)

    async def orderbook_depth(
        self,
        symbol: str,
        depth: int = 50,
    ) -> pd.DataFrame:
        records = []
        for source in self.sources:
            snapshot = await source.fetch_orderbook(symbol, depth=depth)
            if snapshot:
                records.append(snapshot)
        return _orderbook_dataframe(records)


def _append_records(records: list, events: Iterable) -> None:
    for event in events:
        records.append(event)


def _funding_dataframe(events: list[FundingRate]) -> pd.DataFrame:
    if not events:
        return pd.DataFrame(columns=["timestamp", "symbol", "venue", "rate"])
    frame = pd.DataFrame(
        [
            {
                "timestamp": event.timestamp,
                "symbol": event.symbol,
                "venue": event.venue,
                "rate": event.rate,
                **dict(event.extras or {}),
            }
            for event in events
        ]
    )
    frame.sort_values("timestamp", inplace=True)
    frame.reset_index(drop=True, inplace=True)
    return frame


def _open_interest_dataframe(events: list[OpenInterest]) -> pd.DataFrame:
    if not events:
        return pd.DataFrame(columns=["timestamp", "symbol", "venue", "open_interest", "notional"])
    frame = pd.DataFrame(
        [
            {
                "timestamp": event.timestamp,
                "symbol": event.symbol,
                "venue": event.venue,
                "open_interest": event.open_interest,
                "notional": event.notional,
                **dict(event.extras or {}),
            }
            for event in events
        ]
    )
    frame.sort_values("timestamp", inplace=True)
    frame.reset_index(drop=True, inplace=True)
    return frame


def _liquidation_dataframe(events: list[LiquidationEvent]) -> pd.DataFrame:
    if not events:
        return pd.DataFrame(columns=["timestamp", "symbol", "venue", "side", "price", "quantity", "notional"])
    frame = pd.DataFrame(
        [
            {
                "timestamp": event.timestamp,
                "symbol": event.symbol,
                "venue": event.venue,
                "side": event.side,
                "price": event.price,
                "quantity": event.quantity,
                "notional": event.notional,
                **dict(event.extras or {}),
            }
            for event in events
        ]
    )
    frame.sort_values("timestamp", inplace=True)
    frame.reset_index(drop=True, inplace=True)
    return frame


def _orderbook_dataframe(snapshots: list[OrderBookDepth]) -> pd.DataFrame:
    if not snapshots:
        return pd.DataFrame(columns=["timestamp", "symbol", "venue", "best_bid_price", "best_ask_price", "bid_depth", "ask_depth"])
    rows = []
    for snap in snapshots:
        best_bid = snap.best_bid
        best_ask = snap.best_ask
        rows.append(
            {
                "timestamp": snap.timestamp,
                "symbol": snap.symbol,
                "venue": snap.venue,
                "best_bid_price": best_bid.price if best_bid else None,
                "best_bid_qty": best_bid.quantity if best_bid else None,
                "best_ask_price": best_ask.price if best_ask else None,
                "best_ask_qty": best_ask.quantity if best_ask else None,
                "bid_depth": snap.bid_depth,
                "ask_depth": snap.ask_depth,
            }
        )
    frame = pd.DataFrame(rows)
    frame.sort_values("timestamp", inplace=True)
    frame.reset_index(drop=True, inplace=True)
    return frame




