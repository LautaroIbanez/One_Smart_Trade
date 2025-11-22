"""High-resolution order book snapshot collection and repository."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.core.logging import logger
from app.data.exchanges.base import ExchangeDataSource
from app.data.storage import ensure_partition_dirs, get_raw_path, write_parquet


@dataclass
class OrderBookSnapshot:
    """High-resolution order book snapshot with multiple levels."""

    timestamp: pd.Timestamp
    symbol: str
    venue: str
    bids: list[tuple[float, float]]  # (price, qty) sorted descending by price
    asks: list[tuple[float, float]]  # (price, qty) sorted ascending by price

    def __post_init__(self) -> None:
        """Validate and sort bids/asks."""
        # Ensure bids are sorted descending (highest first)
        self.bids = sorted(self.bids, key=lambda x: x[0], reverse=True)
        # Ensure asks are sorted ascending (lowest first)
        self.asks = sorted(self.asks, key=lambda x: x[0])

    @property
    def best_bid(self) -> float | None:
        """Get best bid price."""
        return self.bids[0][0] if self.bids else None

    @property
    def best_ask(self) -> float | None:
        """Get best ask price."""
        return self.asks[0][0] if self.asks else None

    @property
    def mid_price(self) -> float | None:
        """Calculate mid price."""
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2.0
        return None

    @property
    def spread(self) -> float | None:
        """Calculate bid-ask spread."""
        if self.best_bid and self.best_ask:
            return self.best_ask - self.best_bid
        return None

    @property
    def spread_pct(self) -> float | None:
        """Calculate bid-ask spread as percentage."""
        mid = self.mid_price
        spread_abs = self.spread
        if mid and spread_abs:
            return (spread_abs / mid) * 100.0
        return None

    def depth_at_price(self, price: float, side: str = "bid") -> float:
        """Get cumulative depth at or better than given price."""
        if side.lower() == "bid":
            # Sum all bids >= price
            return sum(qty for p, qty in self.bids if p >= price)
        else:
            # Sum all asks <= price
            return sum(qty for p, qty in self.asks if p <= price)

    def depth_notional(self, notional: float, side: str = "bid") -> tuple[float, float]:
        """
        Get price level and cumulative depth for given notional value.
        
        Args:
            notional: Notional value (price * quantity)
            side: "bid" or "ask"
            
        Returns:
            (price_level, cumulative_qty) at which cumulative notional >= notional
        """
        if side.lower() == "bid":
            cumulative_qty = 0.0
            cumulative_notional = 0.0
            for price, qty in self.bids:
                cumulative_qty += qty
                cumulative_notional += price * qty
                if cumulative_notional >= notional:
                    return (price, cumulative_qty)
            # If notional exceeds all bids, return worst bid
            if self.bids:
                return (self.bids[-1][0], cumulative_qty)
            return (0.0, 0.0)
        else:
            cumulative_qty = 0.0
            cumulative_notional = 0.0
            for price, qty in self.asks:
                cumulative_qty += qty
                cumulative_notional += price * qty
                if cumulative_notional >= notional:
                    return (price, cumulative_qty)
            # If notional exceeds all asks, return worst ask
            if self.asks:
                return (self.asks[-1][0], cumulative_qty)
            return (0.0, 0.0)

    def levels(self, n_levels: int = 10) -> dict[str, list[tuple[float, float]]]:
        """Get top N levels for bids and asks."""
        return {
            "bids": self.bids[:n_levels],
            "asks": self.asks[:n_levels],
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "venue": self.venue,
            "bids": self.bids,
            "asks": self.asks,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrderBookSnapshot:
        """Create from dictionary."""
        return cls(
            timestamp=pd.Timestamp(data["timestamp"]),
            symbol=data["symbol"],
            venue=data["venue"],
            bids=[tuple(b) for b in data["bids"]],
            asks=[tuple(a) for a in data["asks"]],
        )


class OrderBookCollector:
    """Collect high-resolution order book snapshots at regular intervals."""

    def __init__(
        self,
        exchange_client: ExchangeDataSource,
        symbol: str,
        *,
        interval_seconds: int = 5,
        depth_levels: int = 10,
        max_levels: int = 50,  # Maximum levels to fetch from exchange
    ) -> None:
        """
        Initialize order book collector.
        
        Args:
            exchange_client: Exchange data source for fetching order books
            symbol: Trading symbol
            interval_seconds: Snapshot interval in seconds (default: 5)
            depth_levels: Number of levels to keep (L1-L10, default: 10)
            max_levels: Maximum levels to fetch from exchange (default: 50)
        """
        self.exchange_client = exchange_client
        self.symbol = symbol
        self.interval_seconds = interval_seconds
        self.depth_levels = depth_levels
        self.max_levels = max_levels
        self.venue = exchange_client.venue

    async def collect_snapshot(self) -> OrderBookSnapshot | None:
        """Collect a single order book snapshot."""
        try:
            # Fetch order book from exchange
            orderbook_depth = await self.exchange_client.fetch_orderbook(
                self.symbol,
                depth=self.max_levels,
            )
            
            if not orderbook_depth:
                logger.warning(f"No order book data for {self.symbol}", extra={"venue": self.venue})
                return None
            
            # Convert OrderBookDepth to list of tuples
            bids = [(level.price, level.quantity) for level in orderbook_depth.bids[:self.depth_levels]]
            asks = [(level.price, level.quantity) for level in orderbook_depth.asks[:self.depth_levels]]
            
            snapshot = OrderBookSnapshot(
                timestamp=pd.Timestamp(orderbook_depth.timestamp),
                symbol=self.symbol,
                venue=self.venue,
                bids=bids,
                asks=asks,
            )
            
            return snapshot
        except Exception as exc:
            logger.error(f"Failed to collect order book snapshot", extra={"symbol": self.symbol, "error": str(exc)})
            return None

    async def collect_period(
        self,
        duration_seconds: int,
        *,
        start_time: datetime | None = None,
    ) -> list[OrderBookSnapshot]:
        """
        Collect snapshots for a period.
        
        Args:
            duration_seconds: Total duration in seconds
            start_time: Optional start time (default: now)
            
        Returns:
            List of collected snapshots
        """
        if start_time is None:
            start_time = datetime.utcnow()
        
        end_time = start_time + timedelta(seconds=duration_seconds)
        snapshots: list[OrderBookSnapshot] = []
        
        current_time = start_time
        
        logger.info(
            f"Starting order book collection for {self.symbol}",
            extra={
                "venue": self.venue,
                "duration_seconds": duration_seconds,
                "interval_seconds": self.interval_seconds,
            },
        )
        
        while current_time < end_time:
            snapshot = await self.collect_snapshot()
            if snapshot:
                snapshots.append(snapshot)
            
            # Wait until next interval
            await asyncio.sleep(self.interval_seconds)
            current_time = datetime.utcnow()
        
        logger.info(
            f"Collected {len(snapshots)} order book snapshots",
            extra={"symbol": self.symbol, "venue": self.venue},
        )
        
        return snapshots


class OrderBookRepository:
    """Repository for reading and querying order book snapshots."""

    def __init__(self, venue: str = "binance", interval: str = "orderbook") -> None:
        """
        Initialize order book repository.
        
        Args:
            venue: Trading venue (default: "binance")
            interval: Data interval identifier (default: "orderbook")
        """
        self.venue = venue
        self.interval = interval

    @staticmethod
    def _parse_levels(levels: Any) -> list[tuple[float, float]]:
        """Parse order book levels from various formats."""
        if isinstance(levels, list):
            # Already a list of tuples/lists
            return [tuple(level) if isinstance(level, (list, tuple)) else (float(level[0]), float(level[1])) for level in levels]
        elif isinstance(levels, str):
            # JSON string
            import json
            try:
                parsed = json.loads(levels)
                return [tuple(level) for level in parsed]
            except Exception:
                return []
        else:
            return []

    def _get_orderbook_path(self, symbol: str) -> Path:
        """Get path to order book parquet file."""
        return get_raw_path(self.venue, symbol, self.interval, filename="orderbook.parquet")

    async def save_snapshots(
        self,
        symbol: str,
        snapshots: list[OrderBookSnapshot],
    ) -> dict[str, Any]:
        """
        Save snapshots to parquet file.
        
        Args:
            symbol: Trading symbol
            snapshots: List of snapshots to save
            
        Returns:
            Dict with save metadata
        """
        if not snapshots:
            return {"status": "no_data", "snapshots": 0}
        
        try:
            # Convert snapshots to DataFrame
            data = []
            for snapshot in snapshots:
                row = {
                    "timestamp": snapshot.timestamp,
                    "symbol": snapshot.symbol,
                    "venue": snapshot.venue,
                    "best_bid": snapshot.best_bid,
                    "best_ask": snapshot.best_ask,
                    "mid_price": snapshot.mid_price,
                    "spread": snapshot.spread,
                    "spread_pct": snapshot.spread_pct,
                    "bids": snapshot.bids,
                    "asks": snapshot.asks,
                    "bid_levels": len(snapshot.bids),
                    "ask_levels": len(snapshot.asks),
                }
                data.append(row)
            
            df = pd.DataFrame(data)
            
            # Ensure partition directories exist
            ensure_partition_dirs(self.venue, symbol, self.interval)
            path = self._get_orderbook_path(symbol)
            
            # Load existing data if file exists
            if path.exists():
                existing_df = pd.read_parquet(path)
                # Combine and deduplicate by timestamp
                df = pd.concat([existing_df, df], ignore_index=True)
                df = df.drop_duplicates(subset=["timestamp"], keep="last")
                df = df.sort_values("timestamp")
            
            # Save to parquet
            result = write_parquet(
                df,
                path,
                metadata={
                    "symbol": symbol,
                    "venue": self.venue,
                    "interval": self.interval,
                    "snapshots": len(snapshots),
                    "depth_levels": len(snapshots[0].bids) if snapshots else 0,
                },
            )
            
            logger.info(
                f"Saved {len(snapshots)} order book snapshots",
                extra={"symbol": symbol, "venue": self.venue, "path": str(path)},
            )
            
            return {
                "status": "ok",
                "snapshots": len(snapshots),
                "path": str(path),
                **result,
            }
        except Exception as exc:
            logger.error(f"Failed to save order book snapshots", extra={"symbol": symbol, "error": str(exc)})
            return {"status": "error", "error": str(exc)}

    async def load(
        self,
        symbol: str,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> list[OrderBookSnapshot]:
        """
        Load snapshots for a time range.
        
        Args:
            symbol: Trading symbol
            start: Start timestamp
            end: End timestamp
            
        Returns:
            List of snapshots in time range
        """
        path = self._get_orderbook_path(symbol)
        
        if not path.exists():
            # Use info level for missing files (expected in fresh environments)
            # Only log once per symbol to avoid spam
            logger.info(f"Orderbook data missing; skipping depth checks", extra={"symbol": symbol, "path": str(path)})
            return []
        
        try:
            df = pd.read_parquet(path)
            
            # Filter by timestamp range
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            mask = (df["timestamp"] >= start) & (df["timestamp"] <= end)
            df_filtered = df[mask].copy()
            
            # Convert to snapshots
            snapshots = []
            for _, row in df_filtered.iterrows():
                snapshot = OrderBookSnapshot(
                    timestamp=row["timestamp"],
                    symbol=row["symbol"],
                    venue=row["venue"],
                    bids=self._parse_levels(row["bids"]),
                    asks=self._parse_levels(row["asks"]),
                )
                snapshots.append(snapshot)
            
            logger.debug(
                f"Loaded {len(snapshots)} snapshots",
                extra={"symbol": symbol, "start": start.isoformat(), "end": end.isoformat()},
            )
            
            return snapshots
        except Exception as exc:
            logger.error(f"Failed to load order book snapshots", extra={"symbol": symbol, "error": str(exc)})
            return []

    async def get_snapshot(
        self,
        symbol: str,
        ts: pd.Timestamp,
        *,
        tolerance_seconds: int = 5,
    ) -> OrderBookSnapshot | None:
        """
        Get snapshot closest to given timestamp.
        
        Args:
            symbol: Trading symbol
            ts: Target timestamp
            tolerance_seconds: Maximum time difference in seconds
            
        Returns:
            Closest snapshot or None
        """
        # Early check: skip if file doesn't exist (graceful fallback)
        path = self._get_orderbook_path(symbol)
        if not path.exists():
            return None
        
        start = ts - pd.Timedelta(seconds=tolerance_seconds)
        end = ts + pd.Timedelta(seconds=tolerance_seconds)
        
        snapshots = await self.load(symbol, start, end)
        
        if not snapshots:
            return None
        
        # Find closest snapshot
        closest = min(snapshots, key=lambda s: abs((s.timestamp - ts).total_seconds()))
        
        # Check if within tolerance
        diff_seconds = abs((closest.timestamp - ts).total_seconds())
        if diff_seconds > tolerance_seconds:
            return None
        
        return closest

    async def get_spread_depth(
        self,
        symbol: str,
        ts: pd.Timestamp,
        notional: float,
        *,
        tolerance_seconds: int = 5,
    ) -> dict[str, Any] | None:
        """
        Get spread and depth information for given notional at timestamp.
        
        Args:
            symbol: Trading symbol
            ts: Target timestamp
            notional: Notional value (price * quantity)
            tolerance_seconds: Maximum time difference in seconds
            
        Returns:
            Dict with spread, depth, and price levels for both sides
        """
        snapshot = await self.get_snapshot(symbol, ts, tolerance_seconds=tolerance_seconds)
        
        if not snapshot:
            return None
        
        # Get depth for both sides
        bid_price, bid_qty = snapshot.depth_notional(notional, side="bid")
        ask_price, ask_qty = snapshot.depth_notional(notional, side="ask")
        
        # Calculate effective spread (includes depth impact)
        effective_spread = ask_price - bid_price if bid_price > 0 and ask_price > 0 else None
        effective_spread_pct = ((effective_spread / snapshot.mid_price) * 100.0) if effective_spread and snapshot.mid_price else None
        
        return {
            "timestamp": snapshot.timestamp.isoformat(),
            "symbol": symbol,
            "notional": notional,
            "best_bid": snapshot.best_bid,
            "best_ask": snapshot.best_ask,
            "spread": snapshot.spread,
            "spread_pct": snapshot.spread_pct,
            "mid_price": snapshot.mid_price,
            "bid_depth": {
                "price": bid_price,
                "quantity": bid_qty,
                "notional": bid_price * bid_qty if bid_price > 0 else 0.0,
            },
            "ask_depth": {
                "price": ask_price,
                "quantity": ask_qty,
                "notional": ask_price * ask_qty if ask_price > 0 else 0.0,
            },
            "effective_spread": effective_spread,
            "effective_spread_pct": effective_spread_pct,
            "levels": {
                "bids": snapshot.levels(n_levels=10)["bids"],
                "asks": snapshot.levels(n_levels=10)["asks"],
            },
        }

    async def get_latest(self, symbol: str) -> OrderBookSnapshot | None:
        """Get most recent snapshot for symbol."""
        path = self._get_orderbook_path(symbol)
        
        if not path.exists():
            return None
        
        try:
            df = pd.read_parquet(path)
            if df.empty:
                return None
            
            # Get latest row
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            latest_row = df.iloc[-1]
            
            snapshot = OrderBookSnapshot(
                timestamp=latest_row["timestamp"],
                symbol=latest_row["symbol"],
                venue=latest_row["venue"],
                bids=self._parse_levels(latest_row["bids"]),
                asks=self._parse_levels(latest_row["asks"]),
            )
            
            return snapshot
        except Exception as exc:
            logger.error(f"Failed to get latest snapshot", extra={"symbol": symbol, "error": str(exc)})
            return None

