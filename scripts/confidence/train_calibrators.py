"""CLI para entrenar calibradores de confianza por régimen."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Sequence

import click
import numpy as np
import pyarrow.dataset as ds

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_PATH = REPO_ROOT / "backend"
if str(BACKEND_PATH) not in sys.path:
    sys.path.append(str(BACKEND_PATH))

from app.confidence.calibrator import (  # noqa: E402
    CalibratorType,
    save_artifact,
    train_calibrator,
)
from app.utils.hashing import get_git_commit_hash  # noqa: E402

ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "confidence"
MANIFEST_FILE = ARTIFACT_ROOT / "manifest.json"


def _normalize_regime(regime: str | None) -> str:
    return (regime or "default").lower()


def _load_dataset(dataset_path: Path, regimes: Sequence[str] | None) -> dict[str, np.ndarray]:
    dataset = ds.dataset(str(dataset_path), format="parquet")
    table = dataset.to_table()
    df = table.to_pandas()
    if df.empty:
        raise click.ClickException("El dataset está vacío, no se puede entrenar calibradores.")
    if regimes:
        df = df[df["market_regime"].str.lower().isin([r.lower() for r in regimes])]
    grouped: dict[str, np.ndarray] = {}
    for regime, subset in df.groupby(df["market_regime"].str.lower()):
        if subset.empty:
            continue
        X = subset["confidence_norm"].to_numpy().reshape(-1, 1)
        y = subset["hit"].astype(int).to_numpy()
        grouped[regime] = (X, y, subset)
    if not grouped:
        raise click.ClickException("No hay registros que coincidan con los filtros solicitados.")
    return grouped


def _ensure_dirs(regime: str) -> Path:
    target_dir = ARTIFACT_ROOT / regime
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


def _append_manifest(entry: dict) -> None:
    manifest = {"calibrators": []}
    if MANIFEST_FILE.exists():
        try:
            manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {"calibrators": []}
    manifest.setdefault("calibrators", []).append(entry)
    MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


@click.command()
@click.option("--dataset-path", type=click.Path(path_type=Path), required=True, help="Ruta al dataset particionado de señales.")
@click.option("--regimes", help="Lista de regímenes a entrenar (calm,balanced,stress,default).", default="")
@click.option("--calibrators", default="platt,isotonic", help="Calibradores a evaluar (platt,isotonic).")
@click.option("--max-ece", type=float, default=0.05, show_default=True, help="ECE máxima aceptada.")
@click.option("--max-brier", type=float, default=0.08, show_default=True, help="Brier Score máximo.")
def main(dataset_path: Path, regimes: str, calibrators: str, max_ece: float, max_brier: float) -> None:
    """Entrena calibradores Platt/Isotónico y guarda artefactos versionados."""
    calibrator_list: list[CalibratorType] = [c.strip().lower() for c in calibrators.split(",") if c.strip()]
    regime_filters = [r.strip().lower() for r in regimes.split(",") if r.strip()] or None
    grouped = _load_dataset(dataset_path, regime_filters)

    for regime, (X, y, subset) in grouped.items():
        best_model = None
        best_metrics = None
        best_type: CalibratorType | None = None
        for cal_type in calibrator_list:
            training = train_calibrator(cal_type, X, y)
            metrics = training["metrics"]
            ece = metrics["ece"]
            brier = metrics["brier"]
            if ece > max_ece or brier > max_brier:
                click.echo(f"Regime {regime} calibrator {cal_type} rejected (ECE={ece:.3f}, Brier={brier:.3f})", err=True)
                continue
            if best_metrics is None or ece < best_metrics["ece"]:
                best_model = training["calibrator"]
                best_metrics = metrics
                best_type = cal_type

        if not best_model or not best_metrics or not best_type:
            click.echo(f"No valid calibrator for regime {regime}; using raw scores.", err=True)
            continue

        regime_dir = _ensure_dirs(regime)
        artifact_path = regime_dir / "calibrator.pkl"
        metadata_path = regime_dir / "metadata.json"
        metadata = {
            "regime": regime,
            "calibrator_type": best_type,
            "ece": best_metrics["ece"],
            "brier": best_metrics["brier"],
            "dataset_path": str(dataset_path),
            "row_count": int(len(subset)),
            "created_at": datetime.utcnow().isoformat(),
            "commit": get_git_commit_hash(),
        }
        save_artifact(best_model, metadata, artifact_path)
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        def _rel(path: Path) -> str:
            try:
                return str(path.relative_to(REPO_ROOT))
            except ValueError:
                return str(path)

        _append_manifest(
            {
                "regime": regime,
                "artifact": _rel(artifact_path),
                "metadata": _rel(metadata_path),
                "metrics": best_metrics,
                "dataset_path": _rel(dataset_path),
                "row_count": metadata["row_count"],
                "calibrator_type": best_type,
                "created_at": metadata["created_at"],
                "commit": metadata["commit"],
            }
        )
        click.echo(f"Calibrador {best_type} guardado para régimen {regime} (ECE={best_metrics['ece']:.3f})")


if __name__ == "__main__":
    main()

