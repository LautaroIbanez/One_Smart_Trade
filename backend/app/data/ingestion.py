from __future__ import annotations

import asyncio
import warnings
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import pandas as pd

# Filter FutureWarnings about deprecated fillna(method=...) to reduce noise
warnings.filterwarnings("ignore", message=".*fillna with 'method' is deprecated.*", category=FutureWarning)

from app.core.logging import logger
from .binance_client import BinanceClient
from .storage import RAW_ROOT, ensure_partition_dirs, get_raw_path, write_parquet
from .universe import AssetSpec

INTERVALS: tuple[str, ...] = ("15m", "30m", "1h", "4h", "1d", "1w")


class DataIngestion:
    """Pipeline to download Binance klines and persist them as parquet."""

    def __init__(self, client: BinanceClient | None = None) -> None:
        self.client = client or BinanceClient()

    def check_gaps(self, interval: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        """Detect missing candles within a timeframe for the given interval."""
        if interval not in INTERVALS:
            return [
                {
                    "status": "error",
                    "interval": interval,
                    "reason": f"Unsupported interval {interval}",
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                }
            ]

        expected_delta = _interval_to_timedelta(interval)
        start_ts = _ensure_utc_timestamp(start)
        end_ts = _ensure_utc_timestamp(end)
        if start_ts >= end_ts:
            return []

        start_dt = start_ts.to_pydatetime()
        end_dt = end_ts.to_pydatetime()

        try:
            from app.data.curation import DataCuration
        except ImportError:
            return [
                {
                    "status": "error",
                    "interval": interval,
                    "reason": "DataCuration import failed",
                    "start": start_dt.isoformat(),
                    "end": end_dt.isoformat(),
                }
            ]

        curator = DataCuration()
        try:
            df = curator.get_historical_curated(interval, start_date=start_dt, end_date=end_dt)
        except FileNotFoundError:
            return [
                {
                    "status": "missing_data",
                    "interval": interval,
                    "reason": "curated_not_found",
                    "start": start_dt.isoformat(),
                    "end": end_dt.isoformat(),
                }
            ]

        if df.empty:
            return [
                {
                    "status": "missing_data",
                    "interval": interval,
                    "reason": "empty_curated",
                    "start": start_dt.isoformat(),
                    "end": end_dt.isoformat(),
                }
            ]

        df = df.sort_values("open_time")
        df = df[(df["open_time"] >= start_ts) & (df["open_time"] <= end_ts)]
        if df.empty:
            return [
                {
                    "status": "missing_data",
                    "interval": interval,
                    "reason": "no_rows_in_range",
                    "start": start_dt.isoformat(),
                    "end": end_dt.isoformat(),
                }
            ]

        gaps: list[dict[str, Any]] = []

        first_timestamp = df["open_time"].iloc[0]
        if first_timestamp - expected_delta > start_ts:
            gaps.append(
                {
                    "status": "gap",
                    "interval": interval,
                    "start": start_dt.isoformat(),
                    "end": (first_timestamp - expected_delta).isoformat(),
                    "missing_candles": int((first_timestamp - start_ts) / expected_delta),
                }
            )

        previous = first_timestamp
        for current in df["open_time"].iloc[1:]:
            delta = current - previous
            if delta > expected_delta:
                gap_start = previous + expected_delta
                gap_end = current - expected_delta
                gaps.append(
                    {
                        "status": "gap",
                        "interval": interval,
                        "start": gap_start.isoformat(),
                        "end": gap_end.isoformat(),
                        "missing_candles": max(int(delta / expected_delta) - 1, 1),
                    }
                )
            previous = current

        last_timestamp = df["open_time"].iloc[-1]
        if last_timestamp + expected_delta < end_ts:
            gaps.append(
                {
                    "status": "gap",
                    "interval": interval,
                    "start": (last_timestamp + expected_delta).isoformat(),
                    "end": end_dt.isoformat(),
                    "missing_candles": int((end_ts - last_timestamp) / expected_delta),
                }
            )

        return gaps

    async def ingest_all_timeframes(
        self, *, symbol: str = "BTCUSDT", venue: str = "binance", end: datetime | None = None
    ) -> list[dict[str, Any]]:
        """
        Ingest all supported timeframes for a specific venue/symbol.
        
        Uses backfill_to_today to ensure we fetch from the last stored timestamp to now,
        preventing BE-DATA-02 errors when no new rows are returned.
        
        Args:
            symbol: Trading symbol (default: "BTCUSDT")
            venue: Trading venue (default: "binance")
            end: End datetime for ingestion. If None, uses datetime.now(timezone.utc) to ensure
                 latest data is included up to the most recent close.
        """
        if end is None:
            end = datetime.now(timezone.utc)
        
        results: list[dict[str, Any]] = []
        for interval in INTERVALS:
            try:
                # BE-DATA-02: Use backfill_to_today to ensure we fetch from last stored timestamp
                # This prevents fetching duplicate data when start is None
                result = await self.backfill_to_today(
                    interval, symbol=symbol, venue=venue
                )
                # Ensure end timestamp is included in result metadata for consistency
                if "meta" in result:
                    result["meta"]["requested_end"] = end.isoformat()
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
        venue: str = "binance",
        limit: int = 1000,
    ) -> dict[str, Any]:
        """
        Ingest data for a specific timeframe, optionally partitioned by venue/symbol.
        
        If venue is provided, uses partitioned paths {venue}/{symbol}/{interval}.
        Otherwise, falls back to legacy flat structure for backward compatibility.
        """
        raw_klines, meta = await self.client.get_klines(symbol, interval, start, end, limit)
        if not raw_klines:
            return {
                "status": "empty",
                "interval": interval,
                "symbol": symbol,
                "venue": venue,
                "rows": 0,
                "meta": meta,
            }

        # Execute blocking pandas operations in thread pool to avoid blocking HTTP requests
        import asyncio
        df = await asyncio.to_thread(self._klines_to_dataframe, raw_klines)
        df["venue"] = venue
        df["symbol"] = symbol
        
        filename = meta["fetched_at"].replace(":", "-")
        if venue:
            output = get_raw_path(venue, symbol, interval, filename=f"{filename}.parquet")
            ensure_partition_dirs(venue, symbol, interval)
        else:
            output = RAW_ROOT / interval / f"{filename}.parquet"
            output.parent.mkdir(parents=True, exist_ok=True)
        
        # Execute blocking file write in thread pool to avoid blocking HTTP requests
        await asyncio.to_thread(
            write_parquet,
            df,
            output,
            meta | {"rows": len(df), "venue": venue, "symbol": symbol},
        )
        return {
            "status": "success",
            "interval": interval,
            "symbol": symbol,
            "venue": venue,
            "rows": len(df),
            "meta": meta,
            "path": str(output),
        }

    async def ingest_asset(
        self,
        asset: AssetSpec,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
        *,
        limit: int = 1000,
    ) -> dict[str, Any]:
        """Ingest data for a specific asset specification."""
        return await self.ingest_timeframe(
            interval,
            start=start,
            end=end,
            symbol=asset.symbol,
            venue=asset.venue,
            limit=limit,
        )
    
    async def backfill_to_today(
        self,
        interval: str,
        *,
        symbol: str = "BTCUSDT",
        venue: str = "binance",
        limit: int = 1000,
    ) -> dict[str, Any]:
        """
        Backfill data from the latest available timestamp to today (now).
        
        This method prioritizes reading from raw data (always up-to-date) and validates
        timestamps to detect stale data. If the latest timestamp is too old, it resets
        to fetch from a recent window.
        
        Args:
            interval: Timeframe to backfill (e.g., '1h', '1d')
            symbol: Trading symbol (default: "BTCUSDT")
            venue: Trading venue (default: "binance")
            limit: Maximum number of candles to fetch per request (default: 1000)
            
        Returns:
            Dict with status, rows ingested, and metadata including fetched_at
        """
        # BE-DATA-02: Prioritize reading from raw data first (always up-to-date)
        # Raw data is the source of truth for latest available timestamp
        start = None
        now = datetime.now(timezone.utc)
        interval_delta = _interval_to_timedelta(interval)
        
        # Define stale thresholds: if latest timestamp is older than this, reset
        stale_thresholds = {
            "15m": timedelta(hours=2),
            "30m": timedelta(hours=4),
            "1h": timedelta(hours=4),
            "4h": timedelta(hours=12),
            "1d": timedelta(days=3),
            "1w": timedelta(days=10),
        }
        stale_threshold = stale_thresholds.get(interval, timedelta(days=1))
        
        try:
            from app.data.storage import get_raw_path, read_parquet
            raw_path = get_raw_path(venue, symbol, interval).parent
            if raw_path.exists():
                raw_files = sorted(raw_path.glob("*.parquet"))
                if raw_files:
                    # Read the most recent raw file to get the latest timestamp
                    last_raw = await asyncio.to_thread(read_parquet, raw_files[-1])
                    if not last_raw.empty and "open_time" in last_raw.columns:
                        latest_timestamp = last_raw["open_time"].max()
                        # Ensure timestamp is timezone-aware UTC
                        if isinstance(latest_timestamp, pd.Timestamp):
                            if latest_timestamp.tz is None:
                                latest_timestamp = latest_timestamp.tz_localize(timezone.utc)
                            else:
                                latest_timestamp = latest_timestamp.tz_convert(timezone.utc)
                            start = latest_timestamp.to_pydatetime()
                        else:
                            start = pd.to_datetime(latest_timestamp).to_pydatetime()
                            if start.tzinfo is None:
                                start = start.replace(tzinfo=timezone.utc)
                        
                        # Validate timestamp freshness
                        age = now - start
                        if age > stale_threshold:
                            logger.warning(
                                f"BE-DATA-02: Latest raw timestamp for {interval} is stale ({age.total_seconds()/3600:.1f}h old, threshold: {stale_threshold.total_seconds()/3600:.1f}h). "
                                f"Resetting to fetch from recent window.",
                                extra={"interval": interval, "venue": venue, "symbol": symbol, "latest_timestamp": start.isoformat(), "age_hours": age.total_seconds()/3600, "threshold_hours": stale_threshold.total_seconds()/3600},
                            )
                            start = None
                        else:
                            logger.debug(
                                f"BE-DATA-02: Found latest raw timestamp for {interval}: {start.isoformat()} (age: {age.total_seconds()/3600:.1f}h)",
                                extra={"interval": interval, "venue": venue, "symbol": symbol, "latest_timestamp": start.isoformat(), "age_hours": age.total_seconds()/3600},
                            )
        except Exception as exc:
            logger.debug(
                f"BE-DATA-02: Could not determine latest raw timestamp for {interval}: {exc}",
                extra={"interval": interval, "venue": venue, "symbol": symbol, "error": str(exc)},
            )
        
        # Fallback to curated data if raw data not available
        if start is None:
            try:
                from app.data.curation import DataCuration
                curator = DataCuration()
                try:
                    df_latest = curator.get_latest_curated(interval, venue=venue, symbol=symbol)
                    if not df_latest.empty and "open_time" in df_latest.columns:
                        latest_timestamp = df_latest["open_time"].max()
                        # Ensure timestamp is timezone-aware UTC
                        if isinstance(latest_timestamp, pd.Timestamp):
                            if latest_timestamp.tz is None:
                                latest_timestamp = latest_timestamp.tz_localize(timezone.utc)
                            else:
                                latest_timestamp = latest_timestamp.tz_convert(timezone.utc)
                            start = latest_timestamp.to_pydatetime()
                        else:
                            start = pd.to_datetime(latest_timestamp).to_pydatetime()
                            if start.tzinfo is None:
                                start = start.replace(tzinfo=timezone.utc)
                        
                        # Validate timestamp freshness (even for curated)
                        age = now - start
                        if age > stale_threshold:
                            logger.warning(
                                f"BE-DATA-02: Latest curated timestamp for {interval} is stale ({age.total_seconds()/3600:.1f}h old). Resetting.",
                                extra={"interval": interval, "venue": venue, "symbol": symbol, "latest_timestamp": start.isoformat(), "age_hours": age.total_seconds()/3600},
                            )
                            start = None
                        else:
                            logger.debug(
                                f"BE-DATA-02: Found latest curated timestamp for {interval}: {start.isoformat()} (age: {age.total_seconds()/3600:.1f}h)",
                                extra={"interval": interval, "venue": venue, "symbol": symbol, "latest_timestamp": start.isoformat(), "age_hours": age.total_seconds()/3600},
                            )
                except FileNotFoundError:
                    logger.debug(
                        f"BE-DATA-02: No curated data found for {interval}",
                        extra={"interval": interval, "venue": venue, "symbol": symbol},
                    )
            except Exception as exc:
                logger.debug(
                    f"BE-DATA-02: Could not determine latest curated timestamp for {interval}: {exc}",
                    extra={"interval": interval, "venue": venue, "symbol": symbol, "error": str(exc)},
                )
        
        # BE-DATA-02: Calculate the start of the next candle after the last stored one
        # This ensures we fetch new candles and avoid duplicates
        if start is not None:
            # Validate that start is not in the future (data corruption check)
            if start > now:
                logger.warning(
                    f"BE-DATA-02: Last stored timestamp ({start.isoformat()}) is in the future for {interval}. Resetting to fetch from beginning.",
                    extra={"interval": interval, "venue": venue, "symbol": symbol, "last_timestamp": start.isoformat(), "now": now.isoformat()},
                )
                start = None
            else:
                # Calculate the start of the next candle by adding the interval duration
                # This ensures we fetch the next candle after the last one stored
                next_candle_start = start + interval_delta
                
                # Ensure we don't request data in the future
                if next_candle_start > now:
                    logger.debug(
                        f"BE-DATA-02: Calculated next candle start ({next_candle_start.isoformat()}) is in the future for {interval}. Using current time minus interval as start.",
                        extra={"interval": interval, "venue": venue, "symbol": symbol, "calculated_start": next_candle_start.isoformat(), "now": now.isoformat()},
                    )
                    # Use a safe start time: current time minus interval duration
                    start = now - interval_delta
                else:
                    start = next_candle_start
            
            if start is not None:
                logger.info(
                    f"BE-DATA-02: Calculated next candle start for {interval}: {start.isoformat()}",
                    extra={"interval": interval, "venue": venue, "symbol": symbol, "next_candle_start": start.isoformat()},
                )
        
        # Compute end as current UTC time
        end = datetime.now(timezone.utc)
        
        logger.debug(
            f"BE-DATA-02: Backfilling {interval} from {start.isoformat() if start else 'beginning'} to {end.isoformat()}",
            extra={"interval": interval, "venue": venue, "symbol": symbol, "start": start.isoformat() if start else None, "end": end.isoformat()},
        )
        
        # Ingest data up to now
        result = await self.ingest_timeframe(
            interval,
            start=start,
            end=end,
            symbol=symbol,
            venue=venue,
            limit=limit,
        )
        
        # Ensure fetched_at is in the result
        if "meta" in result and "fetched_at" in result["meta"]:
            result["fetched_at"] = result["meta"]["fetched_at"]
        else:
            result["fetched_at"] = end.isoformat()
        
        return result

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
        numeric = [
            "open",
            "high",
            "low",
            "close",
            "volume",
            "quote_asset_volume",
            "taker_buy_base",
            "taker_buy_quote",
        ]
        for col in numeric:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["number_of_trades"] = pd.to_numeric(df["number_of_trades"], errors="coerce").fillna(0).astype("int64")
        df[numeric] = df[numeric].ffill().bfill()
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
        df = df.sort_values("open_time").reset_index(drop=True)
        df.dropna(subset=["open", "high", "low", "close"], inplace=True)
        df.drop(columns=["ignore"], inplace=True, errors="ignore")
        return df


def _interval_to_timedelta(interval: str) -> pd.Timedelta:
    mapping = {
        "15m": pd.Timedelta(minutes=15),
        "30m": pd.Timedelta(minutes=30),
        "1h": pd.Timedelta(hours=1),
        "4h": pd.Timedelta(hours=4),
        "1d": pd.Timedelta(days=1),
        "1w": pd.Timedelta(weeks=1),
    }
    return mapping[interval]


def _ensure_utc_timestamp(value: datetime) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts