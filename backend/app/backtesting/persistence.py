"""Persistence layer for backtest results with checksums and reproducibility."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.logging import logger
from app.data.storage import DATA_ROOT


@dataclass
class BacktestRunResult:
    """Canonical backtest run result with metadata."""

    run_id: str
    start_date: str
    end_date: str
    initial_capital: float
    final_capital: float
    trades: list[dict[str, Any]]
    equity_theoretical: list[float]
    equity_realistic: list[float]
    returns_per_period: dict[str, list[float]]
    metadata: dict[str, Any]
    data_hash: str
    seed: int | None
    created_at: datetime
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "run_id": self.run_id,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "initial_capital": self.initial_capital,
            "final_capital": self.final_capital,
            "trades": self.trades,
            "equity_theoretical": self.equity_theoretical,
            "equity_realistic": self.equity_realistic,
            "returns_per_period": self.returns_per_period,
            "metadata": self.metadata,
            "data_hash": self.data_hash,
            "seed": self.seed,
            "created_at": self.created_at.isoformat(),
            "checksum": self.checksum,
        }

    def calculate_checksum(self) -> str:
        """Calculate SHA256 checksum of result data."""
        data_str = json.dumps(
            {
                "start_date": self.start_date,
                "end_date": self.end_date,
                "initial_capital": self.initial_capital,
                "final_capital": self.final_capital,
                "trades": self.trades,
                "equity_theoretical": self.equity_theoretical,
                "equity_realistic": self.equity_realistic,
                "returns_per_period": self.returns_per_period,
                "data_hash": self.data_hash,
                "seed": self.seed,
            },
            sort_keys=True,
        )
        return hashlib.sha256(data_str.encode()).hexdigest()


class BacktestResultRepository:
    """Repository for persisting and loading backtest results."""

    def __init__(self, base_path: Path | None = None) -> None:
        """
        Initialize repository.

        Args:
            base_path: Base path for storage (default: data/backtest_results)
        """
        self.base_path = base_path or (DATA_ROOT / "backtest_results")
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save(self, result: BacktestRunResult, *, format: str = "json") -> dict[str, Any]:
        """
        Save backtest result with checksum.

        Args:
            result: Backtest result to save
            format: Storage format ("json" or "parquet")

        Returns:
            Dict with path, checksum, and metadata
        """
        # Calculate checksum
        result.checksum = result.calculate_checksum()

        # Generate filename
        timestamp = result.created_at.strftime("%Y%m%d_%H%M%S")
        filename = f"backtest_{result.run_id}_{timestamp}"

        if format == "json":
            # Save as JSON
            json_path = self.base_path / f"{filename}.json"
            with json_path.open("w", encoding="utf-8") as f:
                json.dump(result.to_dict(), f, indent=2, default=str)

            # Save checksum separately
            checksum_path = json_path.with_suffix(".checksum")
            checksum_path.write_text(result.checksum, encoding="utf-8")

            logger.info("Backtest result saved", extra={"path": str(json_path), "checksum": result.checksum})

            return {
                "path": str(json_path),
                "checksum": result.checksum,
                "format": "json",
                "run_id": result.run_id,
            }

        elif format == "parquet":
            # Save trades as Parquet
            trades_df = pd.DataFrame(result.trades)
            parquet_path = self.base_path / f"{filename}_trades.parquet"
            trades_df.to_parquet(parquet_path, compression="snappy", index=False)

            # Save metadata and curves as JSON
            metadata_path = self.base_path / f"{filename}_metadata.json"
            metadata_dict = {
                "run_id": result.run_id,
                "start_date": result.start_date,
                "end_date": result.end_date,
                "initial_capital": result.initial_capital,
                "final_capital": result.final_capital,
                "equity_theoretical": result.equity_theoretical,
                "equity_realistic": result.equity_realistic,
                "returns_per_period": result.returns_per_period,
                "metadata": result.metadata,
                "data_hash": result.data_hash,
                "seed": result.seed,
                "created_at": result.created_at.isoformat(),
                "checksum": result.checksum,
            }
            with metadata_path.open("w", encoding="utf-8") as f:
                json.dump(metadata_dict, f, indent=2, default=str)

            # Save checksum
            checksum_path = parquet_path.with_suffix(".checksum")
            checksum_path.write_text(result.checksum, encoding="utf-8")

            logger.info("Backtest result saved", extra={"path": str(parquet_path), "checksum": result.checksum})

            return {
                "path": str(parquet_path),
                "metadata_path": str(metadata_path),
                "checksum": result.checksum,
                "format": "parquet",
                "run_id": result.run_id,
            }

        else:
            raise ValueError(f"Unsupported format: {format}")

    def load(self, run_id: str) -> BacktestRunResult | None:
        """
        Load backtest result by run_id.

        Args:
            run_id: Run ID to load

        Returns:
            BacktestRunResult or None if not found
        """
        # Search for files with this run_id
        pattern = f"backtest_{run_id}_*.json"
        matches = list(self.base_path.glob(pattern))

        if not matches:
            # Try parquet format
            pattern = f"backtest_{run_id}_*_metadata.json"
            matches = list(self.base_path.glob(pattern))

        if not matches:
            logger.warning("Backtest result not found", extra={"run_id": run_id})
            return None

        # Load most recent
        latest = max(matches, key=lambda p: p.stat().st_mtime)

        try:
            with latest.open("r", encoding="utf-8") as f:
                data = json.load(f)

            # Reconstruct result
            result = BacktestRunResult(
                run_id=data["run_id"],
                start_date=data["start_date"],
                end_date=data["end_date"],
                initial_capital=data["initial_capital"],
                final_capital=data["final_capital"],
                trades=data["trades"],
                equity_theoretical=data["equity_theoretical"],
                equity_realistic=data["equity_realistic"],
                returns_per_period=data["returns_per_period"],
                metadata=data["metadata"],
                data_hash=data["data_hash"],
                seed=data.get("seed"),
                created_at=datetime.fromisoformat(data["created_at"]),
                checksum=data.get("checksum", ""),
            )

            # Verify checksum
            calculated = result.calculate_checksum()
            if result.checksum and calculated != result.checksum:
                logger.warning("Checksum mismatch", extra={"run_id": run_id, "expected": result.checksum, "calculated": calculated})

            return result

        except Exception as exc:
            logger.error("Failed to load backtest result", extra={"run_id": run_id, "error": str(exc)})
            return None

    def verify_checksum(self, run_id: str) -> bool:
        """
        Verify checksum of stored result.

        Args:
            run_id: Run ID to verify

        Returns:
            True if checksum is valid
        """
        result = self.load(run_id)
        if not result:
            return False

        calculated = result.calculate_checksum()
        return calculated == result.checksum


def save_backtest_result(
    backtest_result: dict[str, Any],
    *,
    run_id: str | None = None,
    format: str = "json",
) -> dict[str, Any]:
    """
    Convenience function to save backtest result.

    Args:
        backtest_result: Result dict from BacktestEngine.run_backtest()
        run_id: Optional run ID (generates if not provided)
        format: Storage format ("json" or "parquet")

    Returns:
        Dict with path, checksum, and metadata
    """
    if run_id is None:
        run_id = hashlib.md5(
            f"{backtest_result['start_date']}_{backtest_result['end_date']}_{backtest_result.get('data_hash', '')}".encode()
        ).hexdigest()[:12]

    result = BacktestRunResult(
        run_id=run_id,
        start_date=backtest_result["start_date"],
        end_date=backtest_result["end_date"],
        initial_capital=backtest_result["initial_capital"],
        final_capital=backtest_result["final_capital"],
        trades=backtest_result["trades"],
        equity_theoretical=backtest_result.get("equity_theoretical", backtest_result.get("equity_curve", [])),
        equity_realistic=backtest_result.get("equity_realistic", []),
        returns_per_period=backtest_result.get("returns_per_period", {}),
        metadata=backtest_result.get("metadata", {}),
        data_hash=backtest_result.get("data_hash", ""),
        seed=backtest_result.get("seed"),
        created_at=datetime.utcnow(),
    )

    repo = BacktestResultRepository()
    return repo.save(result, format=format)

