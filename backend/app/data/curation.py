from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from .ingestion import INTERVALS
from .storage import CURATED_ROOT, RAW_ROOT, ensure_dirs, read_parquet, write_parquet


class DataCuration:
    """Produce curated datasets with indicators for the quant engine."""

    def __init__(self) -> None:
        ensure_dirs()

    def curate_interval(self, interval: str, *, lookback_files: int = 60) -> dict[str, Any]:
        if interval not in INTERVALS:
            return {
                "status": "error",
                "interval": interval,
                "error": f"Unsupported interval {interval}",
            }
        raw_dir = RAW_ROOT / interval
        files = sorted(raw_dir.glob("*.parquet"))
        if not files:
            return {
                "status": "no_data",
                "interval": interval,
                "error": "No raw files found",
            }

        selected = files[-lookback_files:]
        frames = [read_parquet(path) for path in selected]
        df = pd.concat(frames).drop_duplicates(subset="open_time").reset_index(drop=True)
        if df.empty:
            return {
                "status": "no_data",
                "interval": interval,
                "error": "Raw dataframe empty",
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

        df = self._add_indicators(df)
        df["interval"] = interval
        output = CURATED_ROOT / interval / "latest.parquet"
        output.parent.mkdir(parents=True, exist_ok=True)
        write_parquet(
            df,
            output,
            metadata={
                "interval": interval,
                "rows": len(df),
                "generated_at": datetime.utcnow().isoformat(),
            },
        )
        return {
            "status": "success",
            "interval": interval,
            "rows": len(df),
            "path": str(output),
        }

    def curate_timeframe(self, interval: str, *, lookback_files: int = 60) -> dict[str, Any]:
        """Backward-compatible alias used by scripts/tests."""
        return self.curate_interval(interval, lookback_files=lookback_files)

    def get_latest_curated(self, interval: str) -> pd.DataFrame:
        path = CURATED_ROOT / interval / "latest.parquet"
        if not path.exists():
            raise FileNotFoundError(f"Curated dataset not found for {interval}")
        return read_parquet(path)

    def get_historical_curated(
        self,
        interval: str,
        days: int = 365 * 5,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> pd.DataFrame:
        df = self.get_latest_curated(interval)
        cutoff = df["open_time"].max() - timedelta(days=days)
        filtered = df[df["open_time"] >= cutoff].copy()
        if start_date is not None:
            filtered = filtered[filtered["open_time"] >= start_date]
        if end_date is not None:
            filtered = filtered[filtered["open_time"] <= end_date]
        return filtered.reset_index(drop=True)

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