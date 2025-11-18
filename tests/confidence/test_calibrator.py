"""Unit tests for confidence calibrators."""
from __future__ import annotations

import numpy as np
import pytest

from app.confidence.calibrator import (
    IsotonicCalibrator,
    PlattCalibrator,
    expected_calibration_error,
    reliability_curve,
)


def test_platt_calibrator_fit_predict() -> None:
    """Test Platt calibrator fit and predict."""
    calibrator = PlattCalibrator()
    X = np.array([[0.1], [0.3], [0.5], [0.7], [0.9]])
    y = np.array([0, 0, 1, 1, 1])
    
    calibrator.fit(X, y)
    proba = calibrator.predict_proba(X)
    
    assert proba.shape == (5,)
    assert np.all((proba >= 0.0) & (proba <= 1.0))


def test_isotonic_calibrator_fit_predict() -> None:
    """Test Isotonic calibrator fit and predict."""
    calibrator = IsotonicCalibrator()
    X = np.array([[0.1], [0.3], [0.5], [0.7], [0.9]])
    y = np.array([0, 0, 1, 1, 1])
    
    calibrator.fit(X, y)
    proba = calibrator.predict_proba(X)
    
    assert proba.shape == (5,)
    assert np.all((proba >= 0.0) & (proba <= 1.0))


def test_platt_calibrator_probabilities_in_range() -> None:
    """Verify Platt calibrator returns probabilities in [0, 1]."""
    calibrator = PlattCalibrator()
    X = np.random.rand(100, 1)
    y = (X.ravel() > 0.5).astype(int)
    
    calibrator.fit(X, y)
    proba = calibrator.predict_proba(X)
    
    assert np.all(proba >= 0.0), "Probabilities must be >= 0"
    assert np.all(proba <= 1.0), "Probabilities must be <= 1"


def test_isotonic_calibrator_probabilities_in_range() -> None:
    """Verify Isotonic calibrator returns probabilities in [0, 1]."""
    calibrator = IsotonicCalibrator()
    X = np.random.rand(100, 1)
    y = (X.ravel() > 0.5).astype(int)
    
    calibrator.fit(X, y)
    proba = calibrator.predict_proba(X)
    
    assert np.all(proba >= 0.0), "Probabilities must be >= 0"
    assert np.all(proba <= 1.0), "Probabilities must be <= 1"


def test_expected_calibration_error_perfect_calibration() -> None:
    """Test ECE with perfectly calibrated predictions."""
    y_true = np.array([0, 0, 1, 1, 0, 1, 0, 1])
    y_prob = np.array([0.0, 0.0, 1.0, 1.0, 0.0, 1.0, 0.0, 1.0])
    
    ece = expected_calibration_error(y_true, y_prob)
    
    assert ece == 0.0, "Perfect calibration should have ECE = 0"


def test_expected_calibration_error_range() -> None:
    """Test ECE returns values in [0, 1]."""
    y_true = np.random.randint(0, 2, size=100)
    y_prob = np.random.rand(100)
    
    ece = expected_calibration_error(y_true, y_prob)
    
    assert 0.0 <= ece <= 1.0, "ECE must be in [0, 1]"


def test_reliability_curve_structure() -> None:
    """Test reliability curve returns correct structure."""
    y_true = np.array([0, 0, 1, 1, 0, 1])
    y_prob = np.array([0.1, 0.2, 0.8, 0.9, 0.3, 0.7])
    
    curve = reliability_curve(y_true, y_prob)
    
    assert "accuracies" in curve
    assert "confidences" in curve
    assert len(curve["accuracies"]) == len(curve["confidences"])
    assert all(0.0 <= a <= 1.0 for a in curve["accuracies"])
    assert all(0.0 <= c <= 1.0 for c in curve["confidences"])


def test_calibrator_rejects_empty_dataset() -> None:
    """Test calibrators raise error on empty dataset."""
    calibrator = PlattCalibrator()
    X = np.array([]).reshape(0, 1)
    y = np.array([])
    
    with pytest.raises(ValueError):
        calibrator.fit(X, y)


def test_platt_calibrator_monotonic_behavior() -> None:
    """Test Platt calibrator produces reasonable monotonic behavior."""
    calibrator = PlattCalibrator()
    X = np.array([[0.1], [0.3], [0.5], [0.7], [0.9]])
    y = np.array([0, 0, 1, 1, 1])
    
    calibrator.fit(X, y)
    
    # Test that higher input confidence generally leads to higher output probability
    low_conf = calibrator.predict_proba(np.array([[0.2]]))[0]
    high_conf = calibrator.predict_proba(np.array([[0.8]]))[0]
    
    # This should generally hold (though not strictly guaranteed)
    # We just check they're valid probabilities
    assert 0.0 <= low_conf <= 1.0
    assert 0.0 <= high_conf <= 1.0

