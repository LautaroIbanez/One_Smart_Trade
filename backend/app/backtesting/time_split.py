"""Time-based dataset orchestration to prevent lookahead bias."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Iterable, Literal, Protocol

import pandas as pd


@dataclass(frozen=True, slots=True)
class TimeWindow:
    start: pd.Timestamp
    end: pd.Timestamp
    role: Literal["train", "validation", "test", "wf"]

    def as_datetime_tuple(self) -> tuple[datetime, datetime]:
        return self.start.to_pydatetime(), self.end.to_pydatetime()


class DataLoader(Protocol):
    def load(self, interval: str, start: datetime, end: datetime) -> pd.DataFrame:
        ...


class TimeSplitPipeline:
    """Generate temporally isolated datasets for backtesting workflows."""

    def __init__(self, loader: DataLoader, *, interval: str = "1d", walk_days: int | None = None) -> None:
        self.loader = loader
        self.interval = interval
        self.walk_days = walk_days

    def split(
        self,
        start: datetime,
        end: datetime,
        *,
        train_days: int = 365,
        val_days: int = 90,
        test_days: int = 90,
    ) -> Dict[str, list[TimeWindow]]:
        start_ts = _ensure_timestamp(start)
        end_ts = _ensure_timestamp(end)
        if start_ts >= end_ts:
            raise ValueError("Start must be earlier than end.")

        day = pd.Timedelta(days=1)
        train_end = start_ts + pd.Timedelta(days=train_days - 1)
        if train_end >= end_ts:
            raise ValueError("Training window exceeds available range.")

        val_start = train_end + day
        val_end = val_start + pd.Timedelta(days=val_days - 1)
        if val_end >= end_ts:
            raise ValueError("Validation window exceeds available range.")

        test_end = end_ts
        test_start = end_ts - pd.Timedelta(days=test_days - 1)
        if test_start <= val_end:
            raise ValueError("Test window overlaps validation data; extend overall range or adjust spans.")

        walk_span_days = self.walk_days or test_days
        walk_span_days = max(1, walk_span_days)
        walk_windows: list[TimeWindow] = []
        walk_start = val_end + day
        walk_cutoff = test_start - day
        while walk_start <= walk_cutoff:
            walk_end = min(walk_start + pd.Timedelta(days=walk_span_days - 1), walk_cutoff)
            walk_windows.append(TimeWindow(start=walk_start, end=walk_end, role="wf"))
            walk_start = walk_end + day

        return {
            "train": [TimeWindow(start=start_ts, end=train_end, role="train")],
            "validation": [TimeWindow(start=val_start, end=val_end, role="validation")],
            "test": [TimeWindow(start=test_start, end=test_end, role="test")],
            "walk_forward": walk_windows,
        }

    def materialize(self, window: TimeWindow, *, interval: str | None = None) -> pd.DataFrame:
        frame = self.loader.load(interval or self.interval, window.start.to_pydatetime(), window.end.to_pydatetime())
        if frame.empty:
            return frame
        frame = frame.copy()
        frame.sort_values("open_time", inplace=True)
        frame = frame[frame["open_time"] <= window.end].reset_index(drop=True)
        return frame

    def materialize_many(self, windows: Iterable[TimeWindow], *, interval: str | None = None) -> dict[TimeWindow, pd.DataFrame]:
        data: dict[TimeWindow, pd.DataFrame] = {}
        for window in windows:
            data[window] = self.materialize(window, interval=interval)
        return data


def _ensure_timestamp(value: datetime | pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tz is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts


class CurationDataLoader:
    """Adapter to load curated datasets from DataCuration without leakage."""

    def __init__(self, curation) -> None:
        self.curation = curation

    def load(self, interval: str, start: datetime, end: datetime) -> pd.DataFrame:
        return self.curation.get_historical_curated(interval, start_date=start, end_date=end)

