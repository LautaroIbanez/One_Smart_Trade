"""Model calibration wrappers (Platt scaling & isotonic regression)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import joblib
import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
from sklearn.model_selection import train_test_split

CalibratorType = Literal["platt", "isotonic"]


def expected_calibration_error(y_true: np.ndarray, y_prob: np.ndarray, *, n_bins: int = 10) -> float:
    """Compute Expected Calibration Error (ECE) for binary classification."""
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    total = len(y_true)
    if total == 0:
        return 0.0
    for i in range(n_bins):
        lower, upper = bins[i], bins[i + 1]
        mask = (y_prob >= lower) & (y_prob < upper if i < n_bins - 1 else y_prob <= upper)
        bin_count = np.sum(mask)
        if bin_count == 0:
            continue
        bin_confidence = np.mean(y_prob[mask])
        bin_accuracy = np.mean(y_true[mask])
        ece += (bin_count / total) * abs(bin_accuracy - bin_confidence)
    return float(ece)


def reliability_curve(y_true: np.ndarray, y_prob: np.ndarray, *, n_bins: int = 10) -> dict[str, list[float]]:
    """Return reliability curve points for analysis."""
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    accuracies: list[float] = []
    confidences: list[float] = []
    for i in range(n_bins):
        lower, upper = bins[i], bins[i + 1]
        mask = (y_prob >= lower) & (y_prob < upper if i < n_bins - 1 else y_prob <= upper)
        if not np.any(mask):
            continue
        accuracies.append(float(np.mean(y_true[mask])))
        confidences.append(float(np.mean(y_prob[mask])))
    return {"accuracies": accuracies, "confidences": confidences}


@dataclass
class CalibratorArtifact:
    regime: str
    calibrator_type: CalibratorType
    ece: float
    brier: float
    model_path: Path
    metadata_path: Path


class BaseCalibrator:
    """Abstract wrapper for confidence calibration models."""

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def predict_proba(self, X: np.ndarray) -> np.ndarray:  # pragma: no cover - interface
        raise NotImplementedError


class PlattCalibrator(BaseCalibrator):
    """Logistic regression (Platt scaling)."""

    def __init__(self, *, C: float = 1.0, max_iter: int = 1000):
        self.model = LogisticRegression(C=C, max_iter=max_iter)

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        self.model.fit(X, y)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self.model.predict_proba(X)[:, 1]


class IsotonicCalibrator(BaseCalibrator):
    """Isotonic regression calibrator."""

    def __init__(self):
        self.model = IsotonicRegression(out_of_bounds="clip")

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        X_1d = X.reshape(-1)
        self.model.fit(X_1d, y)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        X_1d = X.reshape(-1)
        return np.asarray(self.model.predict(X_1d))


def train_calibrator(
    calibration_type: CalibratorType,
    X: np.ndarray,
    y: np.ndarray,
    *,
    test_size: float = 0.2,
    random_state: int | None = 42,
) -> dict[str, Any]:
    """Train calibrator and report metrics on holdout set."""
    if len(X) == 0:
        raise ValueError("Dataset vacío para entrenar calibrador")
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=random_state, stratify=y)

    if calibration_type == "platt":
        calibrator = PlattCalibrator()
    elif calibration_type == "isotonic":
        calibrator = IsotonicCalibrator()
    else:
        raise ValueError(f"Tipo de calibrador no soportado: {calibration_type}")

    calibrator.fit(X_train, y_train)
    y_prob = calibrator.predict_proba(X_test)
    y_prob = np.clip(y_prob, 0.0, 1.0)
    brier = brier_score_loss(y_test, y_prob)
    ece = expected_calibration_error(y_test, y_prob)
    curve = reliability_curve(y_test, y_prob)

    return {
        "calibrator": calibrator,
        "metrics": {
            "brier": float(brier),
            "ece": float(ece),
            "reliability_curve": curve,
        },
    }


def save_artifact(calibrator: BaseCalibrator, metadata: dict[str, Any], path: Path) -> None:
    """Persist calibrator artifact to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "calibrator": calibrator,
        "metadata": metadata,
    }
    joblib.dump(payload, path)

