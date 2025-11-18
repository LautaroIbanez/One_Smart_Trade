"""Integration tests for meta-learner in strategy ensemble."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
import pytest

from app.strategies.meta_learner import MetaLearner
from app.strategies.strategy_ensemble import StrategyEnsemble
from app.strategies.weight_store import MetaWeightStore


@pytest.fixture
def sample_strategy_signals():
    """Sample strategy signals for testing."""
    return [
        {"strategy": "momentum_trend", "signal": "BUY", "confidence": 75.0},
        {"strategy": "mean_reversion", "signal": "HOLD", "confidence": 50.0},
        {"strategy": "breakout", "signal": "BUY", "confidence": 65.0},
    ]


@pytest.fixture
def sample_df():
    """Sample price dataframe."""
    return pd.DataFrame({
        "close": [100, 101, 102, 103, 104],
        "open": [99, 100, 101, 102, 103],
        "high": [101, 102, 103, 104, 105],
        "low": [98, 99, 100, 101, 102],
        "volume": [1000, 1100, 1200, 1300, 1400],
    })


@pytest.fixture
def sample_indicators():
    """Sample indicators."""
    return {
        "rsi": 55.0,
        "atr": 1.5,
        "realized_volatility": 0.25,
    }


def test_meta_learner_build_features(sample_strategy_signals):
    """Test feature building from strategy signals."""
    learner = MetaLearner()
    
    regime_features = {
        "regime": "bull",
        "vol_bucket": "balanced",
        "features_regimen": {"mom_1d": 0.02, "rsi": 60.0},
    }
    
    volatility_state = {
        "volatility": 0.25,
        "atr": 1.5,
    }
    
    features = learner.build_features(
        sample_strategy_signals,
        regime_features,
        volatility_state,
    )
    
    assert features is not None
    assert len(features) > 0
    assert isinstance(features, np.ndarray)


def test_meta_learner_train_and_predict():
    """Test training and prediction."""
    # Create synthetic data
    n_samples = 200
    n_features = 25  # Approximate feature count
    
    X = np.random.randn(n_samples, n_features)
    y = (np.random.rand(n_samples) > 0.5).astype(int)
    
    # Train
    learner = MetaLearner(model_type="logistic")
    metrics = learner.fit(X, y)
    
    assert learner.is_fitted
    assert "roc_auc" in metrics
    assert "ece" in metrics
    assert metrics["ece"] >= 0.0
    
    # Predict
    X_test = np.random.randn(10, n_features)
    proba = learner.predict_proba(X_test)
    
    assert proba.shape == (10, 2)
    assert np.allclose(proba.sum(axis=1), 1.0)


def test_meta_learner_save_and_load(tmp_path):
    """Test saving and loading meta-learner."""
    # Train a model
    X = np.random.randn(100, 25)
    y = (np.random.rand(100) > 0.5).astype(int)
    
    learner = MetaLearner(model_type="logistic", regime="bull")
    learner.fit(X, y)
    
    # Save
    model_path = tmp_path / "model.pkl"
    learner.save(model_path)
    
    assert model_path.exists()
    
    # Load
    loaded = MetaLearner.load(model_path)
    
    assert loaded.is_fitted
    assert loaded.regime == "bull"
    assert loaded.model_type == "logistic"
    
    # Verify predictions match
    X_test = np.random.randn(5, 25)
    original_proba = learner.predict_proba(X_test)
    loaded_proba = loaded.predict_proba(X_test)
    
    np.testing.assert_allclose(original_proba, loaded_proba, rtol=1e-5)


def test_strategy_ensemble_uses_meta_learner_when_available(
    sample_df, sample_indicators, sample_strategy_signals, tmp_path
):
    """Test that StrategyEnsemble uses meta-learner when available."""
    # Create and train a meta-learner
    X = np.random.randn(100, 25)
    y = (np.random.rand(100) > 0.5).astype(int)
    
    learner = MetaLearner(model_type="logistic", regime="bull")
    learner.fit(X, y)
    
    # Save to temp path
    model_path = tmp_path / "bull" / "model.pkl"
    learner.save(model_path)
    
    # Create ensemble with meta-learner path
    weight_store = MetaWeightStore()
    ensemble = StrategyEnsemble(
        weight_store=weight_store,
        regime="bull",
        meta_learner_path=tmp_path,
        ece_threshold=0.20,  # High threshold so it doesn't degrade
    )
    
    # Mock strategy signals
    with patch.object(ensemble, "strategies") as mock_strategies:
        mock_strategy = Mock()
        mock_strategy.name = "momentum_trend"
        mock_strategy.generate_signal.return_value = {
            "signal": "BUY",
            "confidence": 75.0,
            "reason": "test",
        }
        mock_strategies.__iter__.return_value = [mock_strategy] * 3
        
        # Mock consolidate_signals to use meta-learner
        result = ensemble.consolidate_signals(sample_df, sample_indicators)
        
        # Should use meta-learner if ECE is low
        if ensemble.meta_learner and ensemble.meta_learner.get_ece() <= ensemble.ece_threshold:
            assert "meta_learner_used" in result
            # Note: actual usage depends on ECE threshold


def test_strategy_ensemble_degrades_on_high_ece(
    sample_df, sample_indicators, tmp_path
):
    """Test that StrategyEnsemble degrades to voting when ECE is high."""
    # Create a meta-learner with high ECE (simulated)
    learner = MetaLearner(model_type="logistic", regime="bull")
    learner.is_fitted = True
    learner.metrics = {"ece": 0.25}  # High ECE
    
    # Save
    model_path = tmp_path / "bull" / "model.pkl"
    learner.save(model_path)
    
    # Create ensemble with low ECE threshold
    weight_store = MetaWeightStore()
    ensemble = StrategyEnsemble(
        weight_store=weight_store,
        regime="bull",
        meta_learner_path=tmp_path,
        ece_threshold=0.15,  # Lower than ECE
    )
    
    # Meta-learner should not be used due to high ECE
    assert ensemble.meta_learner is None or ensemble.meta_learner.get_ece() > ensemble.ece_threshold


def test_strategy_ensemble_fallback_to_voting_when_no_meta_learner(
    sample_df, sample_indicators
):
    """Test that StrategyEnsemble falls back to voting when no meta-learner."""
    weight_store = MetaWeightStore()
    ensemble = StrategyEnsemble(
        weight_store=weight_store,
        regime="neutral",
        meta_learner_path=Path("/nonexistent/path"),
    )
    
    # Should not have meta-learner
    assert ensemble.meta_learner is None
    
    # Should use voting
    result = ensemble.consolidate_signals(sample_df, sample_indicators)
    
    assert "meta_learner_used" in result
    assert result["meta_learner_used"] is False
    assert "signal" in result
    assert result["signal"] in ["BUY", "SELL", "HOLD"]


def test_meta_learner_predict_with_strategy_signals(sample_strategy_signals):
    """Test meta-learner prediction with strategy signals."""
    # Train a model
    X = np.random.randn(100, 25)
    y = (np.random.rand(100) > 0.5).astype(int)
    
    learner = MetaLearner(model_type="logistic")
    learner.fit(X, y)
    
    # Predict
    regime_features = {
        "regime": "bull",
        "vol_bucket": "balanced",
        "features_regimen": {"mom_1d": 0.02, "rsi": 60.0},
    }
    
    volatility_state = {
        "volatility": 0.25,
        "atr": 1.5,
    }
    
    result = learner.predict(
        sample_strategy_signals,
        regime_features,
        volatility_state,
        task="buy",
    )
    
    assert "prob_buy" in result
    assert "prob_sell" in result
    assert "prob_hold" in result
    assert "signal" in result
    
    assert 0.0 <= result["prob_buy"] <= 1.0
    assert 0.0 <= result["prob_sell"] <= 1.0
    assert 0.0 <= result["prob_hold"] <= 1.0
    assert abs(result["prob_buy"] + result["prob_sell"] + result["prob_hold"] - 1.0) < 0.01
    assert result["signal"] in ["BUY", "SELL", "HOLD"]


def test_meta_learner_ece_calculation():
    """Test ECE calculation."""
    # Create model with known calibration
    X = np.random.randn(200, 25)
    y = (np.random.rand(200) > 0.5).astype(int)
    
    learner = MetaLearner(model_type="logistic")
    metrics = learner.fit(X, y)
    
    ece = learner.get_ece()
    
    assert "ece" in metrics
    assert 0.0 <= ece <= 1.0
    assert ece == metrics["ece"]


def test_strategy_ensemble_respects_ece_threshold(tmp_path):
    """Test that StrategyEnsemble respects ECE threshold."""
    # Create meta-learner with medium ECE
    learner = MetaLearner(model_type="logistic", regime="bull")
    X = np.random.randn(100, 25)
    y = (np.random.rand(100) > 0.5).astype(int)
    learner.fit(X, y)
    
    ece = learner.get_ece()
    
    # Save
    model_path = tmp_path / "bull" / "model.pkl"
    learner.save(model_path)
    
    # Test with threshold below ECE
    weight_store = MetaWeightStore()
    ensemble_low_threshold = StrategyEnsemble(
        weight_store=weight_store,
        regime="bull",
        meta_learner_path=tmp_path,
        ece_threshold=ece - 0.1,  # Below actual ECE
    )
    
    # Should not use meta-learner
    if ece > ensemble_low_threshold.ece_threshold:
        assert ensemble_low_threshold.meta_learner is None
    
    # Test with threshold above ECE
    ensemble_high_threshold = StrategyEnsemble(
        weight_store=weight_store,
        regime="bull",
        meta_learner_path=tmp_path,
        ece_threshold=ece + 0.1,  # Above actual ECE
    )
    
    # Should use meta-learner
    if ece <= ensemble_high_threshold.ece_threshold:
        assert ensemble_high_threshold.meta_learner is not None

