from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

DATA_ROOT = Path("data")
RAW_ROOT = DATA_ROOT / "raw"
CURATED_ROOT = DATA_ROOT / "curated"


def ensure_dirs() -> None:
    for directory in (RAW_ROOT, CURATED_ROOT):
        directory.mkdir(parents=True, exist_ok=True)


def write_parquet(df: pd.DataFrame, path: Path, *, metadata: dict[str, Any]) -> None:
    ensure_dirs()
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, compression="snappy", index=False)
    meta_path = path.with_suffix(".meta.json")
    meta_path.write_text(pd.Series(metadata).to_json(indent=2), encoding="utf-8")


def read_parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)