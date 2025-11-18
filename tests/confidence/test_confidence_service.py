from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np

from app.confidence.calibrator import PlattCalibrator
from app.confidence.service import ConfidenceService


def _create_artifact(base_dir: Path, regime: str, *, ece: float = 0.02, brier: float = 0.05) -> None:
    regime_dir = base_dir / regime
    regime_dir.mkdir(parents=True, exist_ok=True)
    calibrator = PlattCalibrator()
    X = np.array([[0.1], [0.2], [0.8], [0.9]])
    y = np.array([0, 0, 1, 1])
    calibrator.fit(X, y)
    metadata = {
        "regime": regime,
        "calibrator_type": "platt",
        "ece": ece,
        "brier": brier,
    }
    joblib.dump({"calibrator": calibrator, "metadata": metadata}, regime_dir / "calibrator.pkl")
    (regime_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")


def test_confidence_service_returns_calibrated_value(tmp_path: Path) -> None:
    _create_artifact(tmp_path, "calm")
    service = ConfidenceService(artifact_root=tmp_path, max_ece=0.05, max_brier=0.08)

    calibrated, metadata = service.calibrate(70.0, regime="calm")

    assert 0.0 <= calibrated <= 100.0
    assert metadata["calibrator_type"] == "platt"


def test_confidence_service_skips_models_above_threshold(tmp_path: Path) -> None:
    _create_artifact(tmp_path, "stress", ece=0.2)
    service = ConfidenceService(artifact_root=tmp_path, max_ece=0.05, max_brier=0.08)

    calibrated, metadata = service.calibrate(60.0, regime="stress")

    assert calibrated == 60.0
    assert metadata == {}

