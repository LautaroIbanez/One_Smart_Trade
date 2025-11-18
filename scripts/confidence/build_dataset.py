"""CLI para construir datasets de calibración desde signal_outcomes."""
from __future__ import annotations

import json
import os
import sys
import uuid
import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

import click
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
from sqlalchemy import select
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_PATH = REPO_ROOT / "backend"
if str(BACKEND_PATH) not in sys.path:
    sys.path.append(str(BACKEND_PATH))

from app.core.database import SessionLocal, Base  # noqa: E402
from app.db.models import SignalOutcomeORM  # noqa: E402
from app.utils.hashing import get_git_commit_hash  # noqa: E402


DEFAULT_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "confidence"
DEFAULT_OUTPUT_DIR = DEFAULT_ARTIFACT_DIR / "datasets"
MANIFEST_PATH = DEFAULT_ARTIFACT_DIR / "datasets.json"


@dataclass
class DatasetFilters:
    start_date: datetime | None = None
    end_date: datetime | None = None
    market_regimes: list[str] | None = None
    vol_buckets: list[str] | None = None


class ConfidenceDatasetBuilder:
    """Encapsula la extracción, transformación y persistencia del dataset."""

    def __init__(
        self,
        session: Session,
        *,
        output_dir: Path = DEFAULT_OUTPUT_DIR,
        manifest_path: Path = MANIFEST_PATH,
    ) -> None:
        self.session = session
        self.output_dir = output_dir
        self.manifest_path = manifest_path
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)

    def build(self, filters: DatasetFilters) -> dict:
        rows = self._fetch_rows(filters)
        if not rows:
            raise click.ClickException("No se encontraron señales con los filtros proporcionados.")
        df = self._normalize_dataframe(rows)
        dataset_path = self._write_partitioned(df)
        metadata = self._persist_manifest(df, dataset_path, filters)
        return metadata

    def _fetch_rows(self, filters: DatasetFilters) -> list[SignalOutcomeORM]:
        stmt = select(SignalOutcomeORM)
        if filters.start_date:
            stmt = stmt.where(SignalOutcomeORM.decision_timestamp >= filters.start_date)
        if filters.end_date:
            stmt = stmt.where(SignalOutcomeORM.decision_timestamp <= filters.end_date)
        if filters.market_regimes:
            stmt = stmt.where(SignalOutcomeORM.market_regime.in_(filters.market_regimes))
        if filters.vol_buckets:
            stmt = stmt.where(SignalOutcomeORM.vol_bucket.in_(filters.vol_buckets))
        stmt = stmt.order_by(SignalOutcomeORM.decision_timestamp.asc())
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def _normalize_dataframe(self, rows: Sequence[SignalOutcomeORM]) -> pd.DataFrame:
        records: list[dict] = []
        for row in rows:
            records.append(
                {
                    "signal_id": row.id,
                    "strategy_id": row.strategy_id,
                    "recommendation_id": row.recommendation_id,
                    "decision_timestamp": row.decision_timestamp,
                    "confidence_raw": float(row.confidence_raw or 0.0),
                    "confidence_calibrated": float(row.confidence_calibrated)
                    if row.confidence_calibrated is not None
                    else None,
                    "market_regime": (row.market_regime or "unknown").lower(),
                    "vol_bucket": (row.vol_bucket or "unknown").lower(),
                    "horizon_minutes": int(row.horizon_minutes or 0),
                    "pnl_pct": float(row.pnl_pct) if row.pnl_pct is not None else None,
                    "outcome": (row.outcome or "open").lower(),
                    "features_regimen": row.features_regimen or {},
                    "metadata": row.metadata or {},
                }
            )
        df = pd.DataFrame.from_records(records)
        if df.empty:
            return df
        df["confidence_raw"] = df["confidence_raw"].clip(lower=0.0, upper=100.0)
        df["confidence_calibrated"] = df["confidence_calibrated"].fillna(df["confidence_raw"]).clip(lower=0.0, upper=100.0)
        df["confidence_norm"] = df["confidence_raw"] / 100.0
        df["confidence_calibrated_norm"] = df["confidence_calibrated"] / 100.0
        df["pnl_pct"] = df["pnl_pct"].fillna(0.0)
        df["pnl_decimal"] = df["pnl_pct"] / 100.0
        df["horizon_minutes"] = df["horizon_minutes"].astype(int)
        df["horizon_hours"] = (df["horizon_minutes"] / 60.0).round(3)
        df["hit"] = ((df["outcome"] == "win") | (df["pnl_pct"] >= 0.0)).astype(int)
        df["horizon_return_pct"] = df["pnl_pct"]
        df["horizon_return_decimal"] = df["pnl_decimal"]
        
        # Features agregadas del régimen
        df = self._compute_aggregated_features(df)
        
        df["features_regimen"] = df["features_regimen"].apply(lambda val: json.dumps(val, sort_keys=True))
        df["metadata"] = df["metadata"].apply(lambda val: json.dumps(val, sort_keys=True))
        return df
    
    def _compute_aggregated_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcular features agregadas por régimen y bucket de volatilidad."""
        if df.empty:
            return df
        
        # Agregar features de régimen desde features_regimen
        def extract_regime_features(features_dict: dict) -> dict:
            if not isinstance(features_dict, dict):
                return {}
            return {
                "momentum_alignment": features_dict.get("momentum_alignment", 0.0),
                "vol_regime_1h": features_dict.get("vol_regime_1h", 1),
                "vol_regime_4h": features_dict.get("vol_regime_4h", 1),
                "vol_regime_1d": features_dict.get("vol_regime_1d", 1),
                "slope_1h": features_dict.get("slope_1h", 0.0),
                "slope_ratio": features_dict.get("slope_ratio", 0.0),
                "mom_1h": features_dict.get("mom_1h", 0.0),
            }
        
        # Extraer features del JSON string si es necesario
        if df["features_regimen"].dtype == "object":
            try:
                features_list = df["features_regimen"].apply(
                    lambda x: extract_regime_features(json.loads(x) if isinstance(x, str) else (x if isinstance(x, dict) else {}))
                )
                for key in ["momentum_alignment", "vol_regime_1h", "vol_regime_4h", "vol_regime_1d", "slope_1h", "slope_ratio", "mom_1h"]:
                    df[f"feature_{key}"] = features_list.apply(lambda d: d.get(key, 0.0))
            except Exception:
                pass
        
        # Features agregadas por régimen y vol_bucket (rolling window)
        df = df.sort_values("decision_timestamp")
        for regime in df["market_regime"].unique():
            regime_mask = df["market_regime"] == regime
            for vol_bucket in df["vol_bucket"].unique():
                bucket_mask = df["vol_bucket"] == vol_bucket
                combined_mask = regime_mask & bucket_mask
                if not combined_mask.any():
                    continue
                
                # Rolling hit rate (últimas 50 señales)
                df.loc[combined_mask, "rolling_hit_rate_50"] = (
                    df.loc[combined_mask, "hit"].rolling(window=50, min_periods=1).mean()
                )
                
                # Rolling confidence promedio
                df.loc[combined_mask, "rolling_confidence_mean_50"] = (
                    df.loc[combined_mask, "confidence_norm"].rolling(window=50, min_periods=1).mean()
                )
                
                # Rolling PnL promedio
                df.loc[combined_mask, "rolling_pnl_mean_50"] = (
                    df.loc[combined_mask, "pnl_decimal"].rolling(window=50, min_periods=1).mean()
                )
        
        # Fill NaN con valores por defecto
        for col in ["rolling_hit_rate_50", "rolling_confidence_mean_50", "rolling_pnl_mean_50"]:
            if col in df.columns:
                df[col] = df[col].fillna(0.0)
        
        return df

    def _write_partitioned(self, df: pd.DataFrame) -> Path:
        dataset_id = uuid.uuid4().hex[:8]
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        target_dir = self.output_dir / f"{timestamp}_{dataset_id}"
        target_dir.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pandas(df)
        ds.write_dataset(
            table,
            base_dir=str(target_dir),
            format="parquet",
            partitioning=ds.partitioning(field_names=["market_regime", "vol_bucket"]),
            existing_data_behavior="overwrite_or_ignore",
        )
        return target_dir

    def _persist_manifest(self, df: pd.DataFrame, dataset_path: Path, filters: DatasetFilters) -> dict:
        query_payload = {
            "start_date": filters.start_date.isoformat() if filters.start_date else None,
            "end_date": filters.end_date.isoformat() if filters.end_date else None,
            "market_regimes": sorted(filters.market_regimes) if filters.market_regimes else None,
            "vol_buckets": sorted(filters.vol_buckets) if filters.vol_buckets else None,
            "row_count": int(len(df)),
        }
        query_hash = hashlib.sha256(json.dumps(query_payload, sort_keys=True).encode("utf-8")).hexdigest()
        try:
            relative_path = str(dataset_path.relative_to(REPO_ROOT))
        except ValueError:
            relative_path = str(dataset_path)
        metadata = {
            "dataset_id": dataset_path.name,
            "path": relative_path,
            "rows": int(len(df)),
            "start_date": query_payload["start_date"],
            "end_date": query_payload["end_date"],
            "market_regimes": query_payload["market_regimes"],
            "vol_buckets": query_payload["vol_buckets"],
            "query_hash": query_hash,
            "commit": get_git_commit_hash(),
            "created_at": datetime.utcnow().isoformat(),
        }
        manifest = {"datasets": []}
        if self.manifest_path.exists():
            try:
                manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                manifest = {"datasets": []}
        manifest.setdefault("datasets", []).append(metadata)
        self.manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return metadata


def _parse_list(ctx, param, value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip().lower() for item in value.split(",") if item.strip()]


@click.command()
@click.option("--start-date", type=click.DateTime(formats=["%Y-%m-%d"]), help="Fecha inicial (UTC) inclusive.")
@click.option("--end-date", type=click.DateTime(formats=["%Y-%m-%d"]), help="Fecha final (UTC) inclusive.")
@click.option(
    "--regimes",
    callback=_parse_list,
    help="Lista separada por comas con los regímenes a filtrar (calm, balanced, stress, unknown).",
)
@click.option(
    "--vol-buckets",
    callback=_parse_list,
    help="Lista separada por comas con buckets de volatilidad (low, balanced, high, unknown).",
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=DEFAULT_OUTPUT_DIR,
    show_default=True,
    help="Directorio base donde se almacenarán los Parquets particionados.",
)
def main(start_date: datetime | None, end_date: datetime | None, regimes: list[str] | None, vol_buckets: list[str] | None, output_dir: Path) -> None:
    """Construye un dataset Parquet particionado para calibración de confianza."""
    filters = DatasetFilters(
        start_date=start_date,
        end_date=end_date,
        market_regimes=regimes,
        vol_buckets=vol_buckets,
    )
    with SessionLocal() as session:
        builder = ConfidenceDatasetBuilder(session, output_dir=output_dir, manifest_path=MANIFEST_PATH)
        metadata = builder.build(filters)
        click.echo(f"Dataset generado: {metadata['path']} ({metadata['rows']} filas)")


if __name__ == "__main__":
    Base.metadata  # ensure metadata import for alembic discovery
    main()

