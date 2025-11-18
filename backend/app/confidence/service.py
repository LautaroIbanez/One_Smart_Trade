"""Runtime service that loads confidence calibrators per regime."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from app.core.logging import logger

DEFAULT_ARTIFACT_ROOT = Path("artifacts/confidence")
DEFAULT_MODEL_FILENAME = "calibrator.pkl"
DEFAULT_METADATA_FILENAME = "metadata.json"


@dataclass
class LoadedCalibrator:
    regime: str
    path: Path
    metadata: dict[str, Any]
    model: Any

    def predict(self, confidence_raw: float) -> float:
        feature = np.array([[confidence_raw / 100.0]])
        try:
            proba = self.model.predict_proba(feature)
        except AttributeError:
            proba = self.model.predict(feature)
        if isinstance(proba, np.ndarray):
            if proba.ndim == 1:
                value = float(proba[0])
            else:
                value = float(proba[0])
        else:
            value = float(proba)
        return float(np.clip(value, 0.0, 1.0))


class ConfidenceService:
    """Provide calibrated probabilities based on market regime."""

    def __init__(
        self,
        *,
        artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
        max_ece: float = 0.05,
        max_brier: float = 0.08,
    ) -> None:
        self.artifact_root = artifact_root
        self.max_ece = max_ece
        self.max_brier = max_brier
        self.calibrators: dict[str, LoadedCalibrator] = {}
        self._load_artifacts()

    def _load_artifacts(self) -> None:
        if not self.artifact_root.exists():
            logger.info("Confidence artifacts directory missing: %s", self.artifact_root)
            return
        for regime_dir in self.artifact_root.iterdir():
            if not regime_dir.is_dir():
                continue
            model_path = regime_dir / DEFAULT_MODEL_FILENAME
            metadata_path = regime_dir / DEFAULT_METADATA_FILENAME
            if not model_path.exists() or not metadata_path.exists():
                logger.debug("Skipping regime %s (missing files)", regime_dir.name)
                continue
            try:
                payload = joblib.load(model_path)
                metadata = joblib.load(metadata_path) if metadata_path.suffix == ".pkl" else {}
                if not metadata:
                    metadata = self._load_metadata_json(metadata_path)
                cal = payload.get("calibrator")
                cal_metadata = payload.get("metadata", {})
                combined_metadata = {**cal_metadata, **metadata}
                if not self._passes_thresholds(combined_metadata):
                    logger.warning(
                        "Skipping calibrator for %s due to metrics (ece=%.4f, brier=%.4f)",
                        regime_dir.name,
                        combined_metadata.get("ece"),
                        combined_metadata.get("brier"),
                    )
                    continue
                loaded = LoadedCalibrator(
                    regime=regime_dir.name.lower(),
                    path=model_path,
                    metadata=combined_metadata,
                    model=cal,
                )
                self.calibrators[loaded.regime] = loaded
            except Exception as exc:
                logger.exception("Failed to load confidence calibrator for %s: %s", regime_dir.name, exc)

    def _load_metadata_json(self, metadata_path: Path) -> dict[str, Any]:
        import json

        try:
            return json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _passes_thresholds(self, metadata: dict[str, Any]) -> bool:
        ece = metadata.get("ece")
        brier = metadata.get("brier")
        if ece is not None and ece > self.max_ece:
            return False
        if brier is not None and brier > self.max_brier:
            return False
        return True

    def calibrate(self, confidence_raw: float, *, regime: str | None = None) -> tuple[float, dict[str, Any]]:
        """Return calibrated confidence (0-100) and metadata."""
        if not self.calibrators:
            return confidence_raw, {}
        regime_key = (regime or "").lower()
        calibrator = self.calibrators.get(regime_key) or self.calibrators.get("default") or self._fallback()
        if not calibrator:
            return confidence_raw, {}
        try:
            raw_value = float(confidence_raw)
        except (TypeError, ValueError):
            raw_value = 0.0
        calibrated = calibrator.predict(raw_value)
        return float(calibrated * 100.0), calibrator.metadata

    def _fallback(self) -> LoadedCalibrator | None:
        if len(self.calibrators) == 1:
            return next(iter(self.calibrators.values()))
        return None

