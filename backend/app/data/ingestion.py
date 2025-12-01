from __future__ import annotations

import warnings
from datetime import datetime, timezone
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
                # Determine start timestamp from latest curated data to avoid re-fetching existing data
                start = None
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
                                latest_dt = latest_timestamp.to_pydatetime()
                            else:
                                latest_dt = pd.to_datetime(latest_timestamp).to_pydatetime()
                                if latest_dt.tzinfo is None:
                                    latest_dt = latest_dt.replace(tzinfo=timezone.utc)
                            
                            # Add one interval to avoid re-fetching the last candle we already have
                            # Binance API is inclusive on startTime, so we need to start after the last candle
                            interval_delta = _interval_to_timedelta(interval)
                            # pd.Timedelta can be added directly to Python datetime, result is still datetime
                            start = latest_dt + interval_delta
                            # Ensure it's a Python datetime (not pd.Timestamp) for Binance client compatibility
                            if isinstance(start, pd.Timestamp):
                                start = start.to_pydatetime()
                            
                            # Only use start if it's before end (otherwise we already have all data)
                            if start >= end:
                                logger.info(
                                    f"Skipping ingestion for {interval}: already have data up to {latest_dt.isoformat()} (end={end.isoformat()})",
                                    extra={
                                        "interval": interval,
                                        "venue": venue,
                                        "symbol": symbol,
                                        "latest_timestamp": latest_dt.isoformat(),
                                        "end": end.isoformat(),
                                    },
                                )
                                results.append({
                                    "status": "skipped",
                                    "interval": interval,
                                    "symbol": symbol,
                                    "venue": venue,
                                    "rows": 0,
                                    "reason": "already_up_to_date",
                                    "latest_timestamp": latest_dt.isoformat(),
                                })
                                continue
                    except FileNotFoundError:
                        # No curated data exists, start from None (will fetch from beginning)
                        start = None
                        logger.info(
                            f"No curated data found for {interval}, starting from beginning",
                            extra={"interval": interval, "venue": venue, "symbol": symbol},
                        )
                except Exception as exc:
                    logger.warning(
                        f"Could not determine latest timestamp for {interval}, starting from beginning: {exc}",
                        extra={"interval": interval, "venue": venue, "symbol": symbol, "error": str(exc)},
                    )
                    start = None
                
                result = await self.ingest_timeframe(
                    interval, start=start, end=end, symbol=symbol, venue=venue
                )
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
            logger.info(
                f"Binance returned empty response for {interval}",
                extra={
                    "interval": interval,
                    "symbol": symbol,
                    "venue": venue,
                    "start": start.isoformat() if start else None,
                    "end": end.isoformat() if end else None,
                    "status_code": "200",
                },
            )
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
        
        # BE-DATA-02: Validate data before writing - detect schema issues early
        if df.empty:
            # Check if we got data from Binance but DataFrame is empty (schema/parsing issue)
            if raw_klines and len(raw_klines) > 0:
                logger.error(
                    f"BE-DATA-02: Schema/parsing issue detected: Binance returned {len(raw_klines)} klines but DataFrame is empty",
                    extra={
                        "interval": interval,
                        "symbol": symbol,
                        "venue": venue,
                        "raw_klines_count": len(raw_klines),
                        "df_rows": len(df),
                        "raw_klines_sample": raw_klines[0] if raw_klines else None,
                        "actionable_error": True,
                        "ingestion_halted": True,
                    },
                )
                return {
                    "status": "error",
                    "interval": interval,
                    "symbol": symbol,
                    "venue": venue,
                    "rows": 0,
                    "error": f"Schema/parsing issue: Binance returned {len(raw_klines)} klines but DataFrame is empty. Check _klines_to_dataframe conversion logic.",
                    "raw_klines_count": len(raw_klines),
                }
            else:
                # No data from Binance - this is expected if already up-to-date
                logger.info(
                    f"No new data from Binance for {interval}",
                    extra={
                        "interval": interval,
                        "symbol": symbol,
                        "venue": venue,
                        "rows": 0,
                        "start": start.isoformat() if start else None,
                        "end": end.isoformat() if end else None,
                    },
                )
        else:
            # Validate required columns exist
            required_columns = ["open_time", "open", "high", "low", "close", "volume"]
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                logger.error(
                    f"BE-DATA-02: Missing required columns in ingested data: {missing_columns}",
                    extra={
                        "interval": interval,
                        "symbol": symbol,
                        "venue": venue,
                        "missing_columns": missing_columns,
                        "available_columns": list(df.columns),
                        "raw_klines_count": len(raw_klines),
                        "actionable_error": True,
                        "ingestion_halted": True,
                    },
                )
                return {
                    "status": "error",
                    "interval": interval,
                    "symbol": symbol,
                    "venue": venue,
                    "rows": 0,
                    "error": f"Missing required columns: {missing_columns}. Available columns: {list(df.columns)}",
                    "missing_columns": missing_columns,
                }
        
        # Log timestamp range of fetched data
        if not df.empty and "open_time" in df.columns:
            min_ts = df["open_time"].min()
            max_ts = df["open_time"].max()
            logger.info(
                f"Ingested {len(df)} rows for {interval}",
                extra={
                    "interval": interval,
                    "symbol": symbol,
                    "venue": venue,
                    "rows": len(df),
                    "min_timestamp": min_ts.isoformat() if hasattr(min_ts, "isoformat") else str(min_ts),
                    "max_timestamp": max_ts.isoformat() if hasattr(max_ts, "isoformat") else str(max_ts),
                    "start": start.isoformat() if start else None,
                    "end": end.isoformat() if end else None,
                },
            )
        else:
            logger.warning(
                f"DataFrame empty or missing open_time after processing for {interval}",
                extra={
                    "interval": interval,
                    "symbol": symbol,
                    "venue": venue,
                    "raw_rows": len(raw_klines),
                    "df_rows": len(df),
                },
            )
        
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
        
        This method computes end=datetime.utcnow() and ensures the fetched_at
        metadata is stored for tracking when data was last updated.
        
        Args:
            interval: Timeframe to backfill (e.g., '1h', '1d')
            symbol: Trading symbol (default: "BTCUSDT")
            venue: Trading venue (default: "binance")
            limit: Maximum number of candles to fetch per request (default: 1000)
            
        Returns:
            Dict with status, rows ingested, and metadata including fetched_at
        """
        # Get latest available timestamp from curated data
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
                else:
                    start = None
            except FileNotFoundError:
                # No curated data exists, start from None (will fetch from beginning)
                start = None
        except Exception as exc:
            logger.warning(f"Could not determine latest timestamp, starting from beginning: {exc}")
            start = None
        
        # Compute end as current UTC time
        end = datetime.now(timezone.utc)
        
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