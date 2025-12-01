from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.logging import logger

DATA_ROOT = Path("data")
RAW_ROOT = DATA_ROOT / "raw"
CURATED_ROOT = DATA_ROOT / "curated"


def ensure_dirs() -> None:
    """Ensure base data directories exist."""
    for directory in (RAW_ROOT, CURATED_ROOT):
        directory.mkdir(parents=True, exist_ok=True)


def get_raw_path(venue: str, symbol: str, interval: str, *, filename: str | None = None) -> Path:
    """Get normalized raw data path: {venue}/{symbol}/{interval}/{filename}."""
    if filename is None:
        filename = "latest.parquet"
    return RAW_ROOT / venue / symbol / interval / filename


def get_curated_path(venue: str, symbol: str, interval: str, *, filename: str | None = None) -> Path:
    """Get normalized curated data path: {venue}/{symbol}/{interval}/{filename}."""
    if filename is None:
        filename = "latest.parquet"
    return CURATED_ROOT / venue / symbol / interval / filename


def ensure_partition_dirs(venue: str, symbol: str, interval: str) -> tuple[Path, Path]:
    """Ensure partition directories exist for both raw and curated data."""
    raw_path = get_raw_path(venue, symbol, interval)
    curated_path = get_curated_path(venue, symbol, interval)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    curated_path.parent.mkdir(parents=True, exist_ok=True)
    return raw_path, curated_path


def write_parquet(df: pd.DataFrame, path: Path, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Write DataFrame to parquet with metadata and audit logging."""
    ensure_dirs()
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, compression="snappy", index=False)
    checksum = _checksum(path)
    payload = dict(metadata or {})
    payload["checksum"] = checksum
    payload.setdefault("rows", len(df))
    meta_path = path.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_audit_log(path, payload)
    return {
        "path": str(path),
        "checksum": checksum,
        "rows": len(df),
        "metadata": payload,
    }


def read_parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_audit_log(path: Path, payload: dict[str, Any]) -> None:
    try:
        log_entry = {
            "path": str(path),
            "checksum": payload.get("checksum"),
            "rows": payload.get("rows", payload.get("metadata", {}).get("rows")),
            "metadata": payload,
        }
        log_dir = path.parent
        log_file = log_dir / "data_audit.log"
        with log_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(log_entry, default=str) + "\n")
    except Exception as exc:
        logger.warning("Failed to append audit log", extra={"path": str(path), "error": str(exc)})