from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from app.core.logging import logger
from .ingestion import INTERVALS
from .quality import CrossVenueReconciler, DataQualityPipeline
from .storage import CURATED_ROOT, RAW_ROOT, ensure_dirs, ensure_partition_dirs, get_curated_path, get_raw_path, read_parquet, write_parquet
from .universe import AssetSpec, MarketUniverseConfig


class DataIntegrityError(Exception):
    """Raised when data quality checks fail."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class DataCuration:
    """Produce curated datasets with indicators for the quant engine."""

    def __init__(
        self,
        universe: MarketUniverseConfig | None = None,
        *,
        quality_config: dict[str, Any] | None = None,
        apply_quality: bool = True,
        apply_reconciler: bool = True,
    ) -> None:
        """
        Initialize data curation pipeline.

        Args:
            universe: Market universe configuration
            quality_config: Quality pipeline configuration
            apply_quality: Whether to apply statistical cleaning (default: True)
            apply_reconciler: Whether to apply cross-venue reconciliation (default: True)
        """
        self.universe = universe
        self.apply_quality = apply_quality
        self.apply_reconciler = apply_reconciler
        self.quality_config = quality_config or {}
        ensure_dirs()

    def curate_interval(
        self,
        interval: str,
        *,
        lookback_files: int = 60,
        venue: str | None = None,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        """
        Curate data for a specific interval, optionally filtered by venue and symbol.
        
        If venue/symbol are provided, uses partitioned paths {venue}/{symbol}/{interval}.
        Otherwise, falls back to legacy flat structure for backward compatibility.
        """
        if interval not in INTERVALS:
            return {
                "status": "error",
                "interval": interval,
                "error": f"Unsupported interval {interval}",
            }

        if venue and symbol:
            raw_dir = get_raw_path(venue, symbol, interval).parent
            curated_path = get_curated_path(venue, symbol, interval)
        else:
            raw_dir = RAW_ROOT / interval
            curated_path = CURATED_ROOT / interval / "latest.parquet"

        files = sorted(raw_dir.glob("*.parquet"))
        if not files:
            return {
                "status": "no_data",
                "interval": interval,
                "error": "No raw files found",
                "venue": venue,
                "symbol": symbol,
            }

        selected = files[-lookback_files:]
        frames = [read_parquet(path) for path in selected]
        df = pd.concat(frames).drop_duplicates(subset="open_time").reset_index(drop=True)
        if df.empty:
            return {
                "status": "no_data",
                "interval": interval,
                "error": "Raw dataframe empty",
                "venue": venue,
                "symbol": symbol,
            }

        numeric_columns = [
            "open",
            "high",
            "low",
            "close",
            "volume",
            "quote_asset_volume",
            "taker_buy_base",
            "taker_buy_quote",
        ]
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        if "number_of_trades" in df.columns:
            df["number_of_trades"] = (
                pd.to_numeric(df["number_of_trades"], errors="coerce")
                .fillna(0)
                .astype("int64")
            )
        df.drop(columns=[c for c in ["ignore"] if c in df.columns], inplace=True)

        df.dropna(subset=["open", "high", "low", "close"], inplace=True)

        # Apply statistical quality pipeline
        quality_stats = {}
        if self.apply_quality:
            quality_pipeline = DataQualityPipeline(
                max_return_z=self.quality_config.get("max_return_z", 6.0),
                max_volume_mad=self.quality_config.get("max_volume_mad", 10.0),
                winsor_limits=tuple(self.quality_config.get("winsor_limits", [0.005, 0.995])),
                interpolation_limit=self.quality_config.get("interpolation_limit", 2),
            )
            
            rows_before = len(df)
            df = quality_pipeline.sanitize(df)
            rows_after = len(df)
            
            quality_stats = {
                "rows_before": rows_before,
                "rows_after": rows_after,
                "rows_removed": rows_before - rows_after,
                "quality_applied": True,
            }
            
            logger.info(
                "Quality pipeline applied",
                extra={
                    "interval": interval,
                    "venue": venue,
                    "symbol": symbol,
                    **quality_stats,
                },
            )

        # Apply cross-venue reconciliation if multi-venue mode
        discrepancies = None
        if self.apply_reconciler and "venue" in df.columns:
            venues = df["venue"].unique()
            if len(venues) > 1:
                reconciler = CrossVenueReconciler(
                    tolerance_bps=self.quality_config.get("tolerance_bps", 5.0),
                    benchmark=self.quality_config.get("benchmark_venue"),
                )
                
                # Split by venue and prepare for reconciliation
                venue_frames = {}
                for v in venues:
                    venue_df = df[df["venue"] == v].copy()
                    if not venue_df.empty:
                        venue_frames[v] = venue_df
                
                if len(venue_frames) > 1:
                    discrepancies_df = reconciler.compare(venue_frames)
                    
                    if not discrepancies_df.empty:
                        discrepancy_rate = len(discrepancies_df) / len(df)
                        max_discrepancy_rate = self.quality_config.get("max_discrepancy_rate", 0.03)
                        
                        logger.warning(
                            "Cross-venue discrepancies detected",
                            extra={
                                "interval": interval,
                                "symbol": symbol,
                                "discrepancy_count": len(discrepancies_df),
                                "discrepancy_rate": discrepancy_rate,
                                "max_allowed": max_discrepancy_rate,
                            },
                        )
                        
                        # Mark reconciled rows
                        df["reconciled_flag"] = True
                        if "open_time" in discrepancies_df.columns:
                            discrepancy_times = set(discrepancies_df["open_time"])
                            df.loc[df["open_time"].isin(discrepancy_times), "reconciled_flag"] = False
                        
                        # Persist discrepancy report
                        self._persist_discrepancy_report(
                            discrepancies_df,
                            interval=interval,
                            venue=venue,
                            symbol=symbol,
                        )
                        
                        # Raise error if discrepancy rate exceeds threshold
                        if discrepancy_rate > max_discrepancy_rate:
                            raise DataIntegrityError(
                                f"Cross-venue discrepancy rate ({discrepancy_rate:.2%}) exceeds maximum ({max_discrepancy_rate:.2%})",
                                details={
                                    "discrepancy_count": len(discrepancies_df),
                                    "discrepancy_rate": discrepancy_rate,
                                    "max_allowed": max_discrepancy_rate,
                                },
                            )
                        
                        discrepancies = {
                            "count": len(discrepancies_df),
                            "rate": discrepancy_rate,
                        }
                    else:
                        df["reconciled_flag"] = True
                        discrepancies = {"count": 0, "rate": 0.0}
                else:
                    df["reconciled_flag"] = True
            else:
                df["reconciled_flag"] = True

        df = self._add_indicators(df)
        df["interval"] = interval
        if venue and symbol:
            df["venue"] = venue
            df["symbol"] = symbol
            ensure_partition_dirs(venue, symbol, interval)

        curated_path.parent.mkdir(parents=True, exist_ok=True)
        write_parquet(
            df,
            curated_path,
            metadata={
                "interval": interval,
                "rows": len(df),
                "generated_at": datetime.utcnow().isoformat(),
                "venue": venue,
                "symbol": symbol,
            },
        )
        result = {
            "status": "success",
            "interval": interval,
            "rows": len(df),
            "path": str(curated_path),
            "venue": venue,
            "symbol": symbol,
            "quality_stats": quality_stats,
            "discrepancies": discrepancies,
            "quality_pass": True,
        }
        
        # Update metadata with quality flags
        metadata = {
            "interval": interval,
            "rows": len(df),
            "generated_at": datetime.utcnow().isoformat(),
            "venue": venue,
            "symbol": symbol,
            "quality_applied": self.apply_quality,
            "reconciler_applied": self.apply_reconciler,
            "quality_pass": True,
        }
        if quality_stats:
            metadata["quality_stats"] = quality_stats
        if discrepancies:
            metadata["discrepancies"] = discrepancies
        
        # Re-write with updated metadata
        write_parquet(
            df,
            curated_path,
            metadata=metadata,
        )
        
        return result

    def curate_timeframe(self, interval: str, *, lookback_files: int = 60) -> dict[str, Any]:
        """Backward-compatible alias used by scripts/tests."""
        return self.curate_interval(interval, lookback_files=lookback_files)

    def get_latest_curated(
        self,
        interval: str,
        *,
        venue: str | None = None,
        symbol: str | None = None,
    ) -> pd.DataFrame:
        """
        Get latest curated dataset for interval, optionally filtered by venue/symbol.
        
        Falls back to legacy flat structure if venue/symbol not provided.
        """
        if venue and symbol:
            path = get_curated_path(venue, symbol, interval)
        else:
            path = CURATED_ROOT / interval / "latest.parquet"
        if not path.exists():
            raise FileNotFoundError(f"Curated dataset not found for {interval} (venue={venue}, symbol={symbol})")
        return read_parquet(path)

    def get_historical_curated(
        self,
        interval: str,
        days: int = 365 * 5,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        *,
        venue: str | None = None,
        symbol: str | None = None,
    ) -> pd.DataFrame:
        """
        Get historical curated data with optional venue/symbol filtering.
        
        Falls back to legacy flat structure if venue/symbol not provided.
        """
        df = self.get_latest_curated(interval, venue=venue, symbol=symbol)
        cutoff = df["open_time"].max() - timedelta(days=days)
        filtered = df[df["open_time"] >= cutoff].copy()
        if start_date is not None:
            filtered = filtered[filtered["open_time"] >= start_date]
        if end_date is not None:
            filtered = filtered[filtered["open_time"] <= end_date]
        return filtered.reset_index(drop=True)

    def curate_asset(
        self,
        asset: AssetSpec,
        interval: str,
        *,
        lookback_files: int = 60,
    ) -> dict[str, Any]:
        """Curate data for a specific asset specification."""
        return self.curate_interval(
            interval,
            lookback_files=lookback_files,
            venue=asset.venue,
            symbol=asset.symbol,
        )

    def curate_universe(
        self,
        interval: str,
        *,
        lookback_files: int = 60,
        universe: MarketUniverseConfig | None = None,
    ) -> dict[str, dict[str, Any]]:
        """
        Curate data for all assets in the universe.
        
        Returns a nested dict: {asset.symbol: {status, ...}}
        """
        config = universe or self.universe
        if config is None:
            raise ValueError("Universe configuration required for curate_universe")
        
        results: dict[str, dict[str, Any]] = {}
        for asset in config.assets:
            result = self.curate_asset(asset, interval, lookback_files=lookback_files)
            results[asset.symbol] = result
        return results

    def _add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        data = df.copy()
        data["returns"] = data["close"].pct_change()

        data["sma_20"] = data["close"].rolling(window=20, min_periods=20).mean()
        data["sma_50"] = data["close"].rolling(window=50, min_periods=50).mean()
        data["ema_21"] = data["close"].ewm(span=21, adjust=False).mean()
        data["ema_55"] = data["close"].ewm(span=55, adjust=False).mean()

        delta = data["close"].diff()
        gain = delta.clip(lower=0.0).rolling(window=14, min_periods=14).mean()
        loss = (-delta.clip(upper=0.0)).rolling(window=14, min_periods=14).mean()
        rs = gain / loss.replace({0: np.nan})
        data["rsi_14"] = 100 - (100 / (1 + rs))

        data["atr_14"] = self._atr(data, period=14)
        data["bollinger_mid"] = data["close"].rolling(window=20, min_periods=20).mean()
        data["bollinger_std"] = data["close"].rolling(window=20, min_periods=20).std()
        data["bollinger_upper"] = data["bollinger_mid"] + 2 * data["bollinger_std"]
        data["bollinger_lower"] = data["bollinger_mid"] - 2 * data["bollinger_std"]

        typical_price = (data["high"] + data["low"] + data["close"]) / 3
        cumulative_volume = data["volume"].cumsum()
        data["vwap"] = (typical_price * data["volume"]).cumsum() / cumulative_volume.replace({0: np.nan})

        data["support"] = data["low"].rolling(window=20, min_periods=20).min()
        data["resistance"] = data["high"].rolling(window=20, min_periods=20).max()
        data["volatility_30"] = data["returns"].rolling(window=30, min_periods=30).std() * np.sqrt(30)

        data["realized_vol_7"] = (
            data["returns"].rolling(window=7, min_periods=7).std() * np.sqrt(365)
        )
        data["realized_vol_90"] = (
            data["returns"].rolling(window=90, min_periods=90).std() * np.sqrt(365)
        )
        data["volume_imbalance"] = (
            data["taker_buy_base"] - (data["volume"] - data["taker_buy_base"])
        ) / data["volume"].replace({0: np.nan})
        data["rolling_vwap_anchored"] = (
            typical_price.rolling(window=55, min_periods=30)
            .apply(lambda x: np.average(x, weights=data["volume"].loc[x.index]))
        )
        data["hl_range_pct"] = (data["high"] - data["low"]) / data["close"]
        data["buy_volume_ratio"] = data["taker_buy_base"] / data["volume"].replace({0: np.nan})

        bid_price_candidates = ["best_bid_price", "bid_price", "bid"]
        ask_price_candidates = ["best_ask_price", "ask_price", "ask"]
        bid_qty_candidates = ["best_bid_qty", "bid_qty", "bid_volume"]
        ask_qty_candidates = ["best_ask_qty", "ask_qty", "ask_volume"]

        bid_price_series = next((data[c] for c in bid_price_candidates if c in data.columns), data["close"])
        ask_price_series = next((data[c] for c in ask_price_candidates if c in data.columns), data["close"])
        bid_qty_series = next((data[c] for c in bid_qty_candidates if c in data.columns), data["taker_buy_base"])
        ask_qty_series = next(
            (data[c] for c in ask_qty_candidates if c in data.columns),
            (data["volume"] - data["taker_buy_base"]),
        )

        data["mid_price"] = (bid_price_series + ask_price_series) / 2
        spread_denominator = data["mid_price"].replace({0: np.nan})
        data["spread_pct"] = (ask_price_series - bid_price_series) / spread_denominator
        depth_total = (bid_qty_series + ask_qty_series).replace({0: np.nan})
        data["orderbook_imbalance"] = (bid_qty_series - ask_qty_series) / depth_total
        data["liquidity_pressure"] = (ask_qty_series / depth_total) - (bid_qty_series / depth_total)

        data["atr_multiple_sl"] = data["close"] - 1.5 * data["atr_14"]
        data["atr_multiple_tp"] = data["close"] + 2.5 * data["atr_14"]
        data.dropna(inplace=True)
        data.reset_index(drop=True, inplace=True)
        return data

    def _atr(self, df: pd.DataFrame, period: int) -> pd.Series:
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return true_range.rolling(window=period, min_periods=period).mean()

    def _persist_discrepancy_report(
        self,
        discrepancies_df: pd.DataFrame,
        *,
        interval: str,
        venue: str | None,
        symbol: str | None,
    ) -> None:
        """Persist discrepancy report to audit directory."""
        from pathlib import Path
        import json

        audit_dir = Path("data/audits")
        if venue and symbol:
            audit_dir = audit_dir / venue / symbol
        else:
            audit_dir = audit_dir / "default"
        
        audit_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        report_path = audit_dir / f"discrepancies_{interval}_{timestamp}.json"
        
        report = {
            "timestamp": timestamp,
            "interval": interval,
            "venue": venue,
            "symbol": symbol,
            "discrepancy_count": len(discrepancies_df),
            "discrepancies": discrepancies_df.to_dict(orient="records"),
        }
        
        report_path.write_text(json.dumps(report, indent=2, default=str))
        logger.info(f"Discrepancy report persisted to {report_path}")