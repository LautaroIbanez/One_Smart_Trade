"""Data quality pipeline for sanitising and reconciling multi-venue datasets."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass(slots=True)
class DataQualityPipeline:
    """Apply statistical cleaning to time series."""

    max_return_z: float = 6.0
    max_volume_mad: float = 10.0
    winsor_limits: tuple[float, float] = (0.005, 0.995)
    interpolation_limit: int = 2

    def sanitize(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df.copy()

        data = df.copy()
        data.sort_values("open_time", inplace=True)
        data.reset_index(drop=True, inplace=True)

        data["log_return"] = np.log(data["close"]).diff()
        return_std = data["log_return"].std(ddof=1)
        if return_std and not np.isclose(return_std, 0.0):
            z_scores = (data["log_return"] - data["log_return"].mean()) / return_std
            mask_returns = z_scores.abs() > self.max_return_z
            data.loc[mask_returns, ["open", "high", "low", "close"]] = np.nan

        if "volume" in data.columns:
            mad = self._median_abs_deviation(data["volume"].dropna())
            if mad and not np.isclose(mad, 0.0):
                volume_dev = (data["volume"] - data["volume"].median()).abs() / mad
                data.loc[volume_dev > self.max_volume_mad, "volume"] = np.nan

        data = self._winsorize(data)

        data.interpolate(method="time", limit=self.interpolation_limit, inplace=True)
        data.ffill(inplace=True)
        data.bfill(inplace=True)

        data.drop(columns=["log_return"], inplace=True, errors="ignore")
        return data

    def _winsorize(self, df: pd.DataFrame) -> pd.DataFrame:
        lower, upper = self.winsor_limits
        if not 0 <= lower < upper <= 1:
            return df
        price_columns = [col for col in ("open", "high", "low", "close") if col in df.columns]
        for col in price_columns:
            series = df[col].dropna()
            if series.empty:
                continue
            lower_bound = series.quantile(lower)
            upper_bound = series.quantile(upper)
            df[col] = df[col].clip(lower=lower_bound, upper=upper_bound)
        return df

    @staticmethod
    def _median_abs_deviation(series: pd.Series) -> float:
        if series.empty:
            return 0.0
        median = series.median()
        deviations = (series - median).abs()
        return float(deviations.median())


@dataclass(slots=True)
class CrossVenueReconciler:
    """Compare multi-venue datasets and flag discrepancies."""

    tolerance_bps: float = 5.0
    benchmark: str | None = None

    def compare(self, frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
        aligned = self._align(frames)
        if aligned.empty:
            return aligned

        venues = [col for col in aligned.columns if col.endswith("_close")]
        benchmark_name = (
            f"{self.benchmark}_close" if self.benchmark else min(venues, key=lambda c: c.split("_")[0])
        )
        benchmark_series = aligned[benchmark_name].replace({0: np.nan})

        diff_columns: list[str] = []
        for col in venues:
            symbol = col.replace("_close", "")
            diff_bps = (aligned[col] / benchmark_series - 1.0) * 10_000
            diff_col = f"{symbol}_close_diff_bps"
            aligned[diff_col] = diff_bps.abs()
            diff_columns.append(diff_col)

        volume_columns = [col for col in aligned.columns if col.endswith("_volume")]
        for col in volume_columns:
            symbol = col.replace("_volume", "")
            diff = (aligned[col] - aligned[f"{self._benchmark_symbol(benchmark_name)}_volume"]).abs()
            aligned[f"{symbol}_volume_diff"] = diff

        aligned["breach"] = aligned.loc[:, diff_columns].max(axis=1) > self.tolerance_bps
        return aligned[aligned["breach"]]

    def _align(self, frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
        if not frames:
            return pd.DataFrame()

        prepared: dict[str, pd.DataFrame] = {}
        for venue, frame in frames.items():
            if frame.empty:
                continue
            data = frame.copy()
            data.sort_values("open_time", inplace=True)
            data = data[["open_time", "close", "volume"]]
            data.rename(columns={"close": f"{venue}_close", "volume": f"{venue}_volume"}, inplace=True)
            prepared[venue] = data

        if not prepared:
            return pd.DataFrame()

        merged = None
        for venue, frame in prepared.items():
            merged = frame if merged is None else pd.merge(merged, frame, on="open_time", how="outer")

        merged.sort_values("open_time", inplace=True)
        merged.reset_index(drop=True, inplace=True)
        merged.ffill(inplace=True)
        merged.bfill(inplace=True)
        return merged

    @staticmethod
    def _benchmark_symbol(benchmark_col: str) -> str:
        return benchmark_col.replace("_close", "")


