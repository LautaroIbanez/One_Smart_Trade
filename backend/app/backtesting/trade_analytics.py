"""Trade-level analytics helpers for MAE/MFE persistence."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.logging import logger
from app.data.storage import DATA_ROOT, write_parquet


@dataclass
class TradeAnalyticsRecord:
    """Canonical record summarizing MAE/MFE statistics for a trade."""

    run_id: str
    trade_id: str
    symbol: str
    side: str
    opened_at: pd.Timestamp
    closed_at: pd.Timestamp | None
    mae: float
    mfe: float
    mae_pct: float
    mfe_pct: float
    strategy_id: str | None = None
    regime: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "run_id": self.run_id,
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side,
            "opened_at": self.opened_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "mae": self.mae,
            "mfe": self.mfe,
            "mae_pct": self.mae_pct,
            "mfe_pct": self.mfe_pct,
            "strategy_id": self.strategy_id,
            "regime": self.regime,
        }
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


class TradeAnalyticsRepository:
    """Persistence layer for trade analytics datasets."""

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or (DATA_ROOT / "analytics" / "trades")
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save_records(self, records: list[TradeAnalyticsRecord], *, filename: str) -> Path | None:
        """Persist records to parquet with audit metadata."""
        if not records:
            logger.info("No trade analytics records to persist", extra={"filename": filename})
            return None

        df = pd.DataFrame([record.to_dict() for record in records])
        path = self.base_path / f"{filename}.parquet"
        write_parquet(df, path, metadata={"rows": len(df), "filename": filename})
        logger.info("Trade analytics saved", extra={"path": str(path), "rows": len(df)})
        return path

    def load_latest(self) -> pd.DataFrame | None:
        """Load the most recent analytics parquet file."""
        files = sorted(self.base_path.glob("*.parquet"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            return None
        latest = files[0]
        try:
            return pd.read_parquet(latest)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to load trade analytics parquet", extra={"path": str(latest), "error": str(exc)})
            return None


