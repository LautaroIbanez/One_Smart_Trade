"""Tests for strategy ensemble dynamic weights."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.db.models import EnsembleWeightORM, SignalOutcomeORM
from app.strategies.strategy_ensemble import StrategyEnsemble
from app.strategies.weight_store import MetaWeightStore
from app.strategies.weight_updater import WeightUpdater


@pytest.fixture
def db_session():
    """Create a test database session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def weight_store(db_session: Session):
    """Create a weight store for testing."""
    return MetaWeightStore(session=db_session)


@pytest.fixture
def sample_strategies():
    """Sample strategy names."""
    return ["momentum_trend", "mean_reversion", "breakout"]


def test_weight_store_save_and_load(weight_store: MetaWeightStore, sample_strategies):
    """Test saving and loading weights."""
    regime = "bull"
    weights = {name: 0.4 if name == "momentum_trend" else 0.3 for name in sample_strategies}
    metrics = {
        name: {
            "sharpe": 1.5 if name == "momentum_trend" else 1.0,
            "calmar": 2.0 if name == "momentum_trend" else 1.5,
            "hit_rate": 60.0 if name == "momentum_trend" else 55.0,
            "max_drawdown": 10.0,
        }
        for name in sample_strategies
    }
    
    # Save weights
    weight_store.save(regime=regime, weights=weights, metrics=metrics)
    
    # Load weights
    loaded = weight_store.load(regime=regime)
    
    assert loaded is not None
    assert len(loaded) == len(sample_strategies)
    for name in sample_strategies:
        assert name in loaded
        assert abs(loaded[name] - weights[name]) < 0.01  # Allow small floating point differences


def test_weight_store_fallback_to_latest(weight_store: MetaWeightStore, sample_strategies):
    """Test fallback to latest weights when regime not found."""
    # Save weights for "bull" regime
    weights_bull = {name: 0.4 if name == "momentum_trend" else 0.3 for name in sample_strategies}
    metrics = {name: {"sharpe": 1.5, "calmar": 2.0} for name in sample_strategies}
    weight_store.save(regime="bull", weights=weights_bull, metrics=metrics)
    
    # Try to load "bear" regime (should fallback to "bull")
    loaded = weight_store.load(regime="bear", fallback_to_latest=True)
    
    assert loaded is not None
    assert len(loaded) == len(sample_strategies)


def test_weight_store_fallback_to_uniform(weight_store: MetaWeightStore, sample_strategies):
    """Test fallback to uniform weights when no weights exist."""
    loaded = weight_store.load(regime="neutral", fallback_to_latest=False)
    
    assert loaded is None


def test_weight_updater_calculate_weights(weight_store: MetaWeightStore, db_session: Session):
    """Test weight calculation from metrics."""
    updater = WeightUpdater(session=db_session, weight_store=weight_store)
    
    # Mock strategy metrics
    strategy_metrics = {
        "momentum_trend": {
            "sharpe": 2.0,
            "calmar": 3.0,
            "hit_rate": 65.0,
            "max_drawdown": 8.0,
            "avg_pnl": 1.5,
        },
        "mean_reversion": {
            "sharpe": 1.0,
            "calmar": 1.5,
            "hit_rate": 55.0,
            "max_drawdown": 12.0,
            "avg_pnl": 0.8,
        },
        "breakout": {
            "sharpe": 1.5,
            "calmar": 2.0,
            "hit_rate": 60.0,
            "max_drawdown": 10.0,
            "avg_pnl": 1.2,
        },
    }
    
    # Calculate weights using softmax_sharpe
    weights = updater.calculate_weights(strategy_metrics, method="softmax_sharpe")
    
    assert weights is not None
    assert len(weights) == 3
    assert abs(sum(weights.values()) - 1.0) < 0.01  # Should sum to 1.0
    
    # Momentum should have highest weight (highest Sharpe)
    assert weights["momentum_trend"] > weights["mean_reversion"]
    assert weights["momentum_trend"] > weights["breakout"]


def test_weight_updater_represents_after_metric_change(
    weight_store: MetaWeightStore, db_session: Session
):
    """Test that weights are reponderated after metric changes."""
    updater = WeightUpdater(session=db_session, weight_store=weight_store)
    
    # Initial metrics: momentum is best
    metrics_initial = {
        "momentum_trend": {"sharpe": 2.0, "max_drawdown": 8.0},
        "mean_reversion": {"sharpe": 1.0, "max_drawdown": 12.0},
        "breakout": {"sharpe": 1.5, "max_drawdown": 10.0},
    }
    
    weights_initial = updater.calculate_weights(metrics_initial, method="softmax_sharpe")
    
    # Later metrics: mean_reversion improves significantly
    metrics_later = {
        "momentum_trend": {"sharpe": 1.5, "max_drawdown": 15.0},  # Worse
        "mean_reversion": {"sharpe": 2.5, "max_drawdown": 8.0},  # Better
        "breakout": {"sharpe": 1.5, "max_drawdown": 10.0},  # Same
    }
    
    weights_later = updater.calculate_weights(metrics_later, method="softmax_sharpe")
    
    # Mean reversion should have higher weight in later scenario
    assert weights_later["mean_reversion"] > weights_initial["mean_reversion"]
    
    # Momentum should have lower weight in later scenario
    assert weights_later["momentum_trend"] < weights_initial["momentum_trend"]


def test_strategy_ensemble_loads_dynamic_weights(weight_store: MetaWeightStore, sample_strategies):
    """Test that StrategyEnsemble loads dynamic weights."""
    # Save weights
    weights = {name: 0.4 if name == "momentum_trend" else 0.3 for name in sample_strategies}
    metrics = {name: {"sharpe": 1.5, "calmar": 2.0} for name in sample_strategies}
    weight_store.save(regime="bull", weights=weights, metrics=metrics)
    
    # Create ensemble with weight store
    ensemble = StrategyEnsemble(weight_store=weight_store, regime="bull")
    
    # Check that weights are loaded
    assert ensemble.strategy_weights is not None
    assert len(ensemble.strategy_weights) == len(sample_strategies)
    
    # Momentum should have higher weight
    assert ensemble.strategy_weights["momentum_trend"] > ensemble.strategy_weights["mean_reversion"]


def test_strategy_ensemble_fallback_to_uniform(weight_store: MetaWeightStore):
    """Test that StrategyEnsemble falls back to uniform weights when no weights exist."""
    # Create ensemble without saving weights first
    ensemble = StrategyEnsemble(weight_store=weight_store, regime="neutral")
    
    # Should have uniform weights
    assert ensemble.strategy_weights is not None
    num_strategies = len(ensemble.strategies)
    expected_weight = 1.0 / num_strategies
    
    for weight in ensemble.strategy_weights.values():
        assert abs(weight - expected_weight) < 0.01


@patch("app.strategies.strategy_ensemble.RegimeClassifier")
def test_strategy_ensemble_auto_detects_regime(mock_classifier, weight_store: MetaWeightStore):
    """Test that StrategyEnsemble auto-detects regime when not provided."""
    import pandas as pd
    
    # Mock regime classifier
    mock_proba = pd.DataFrame({
        "calm": [0.7],
        "balanced": [0.2],
        "stress": [0.1],
    })
    mock_classifier.return_value.fit_predict_proba.return_value = mock_proba
    
    # Create ensemble without regime
    ensemble = StrategyEnsemble(weight_store=weight_store, regime=None)
    
    # Create mock dataframe
    df = pd.DataFrame({
        "close": [100, 101, 102, 103, 104],
        "open": [99, 100, 101, 102, 103],
        "high": [101, 102, 103, 104, 105],
        "low": [98, 99, 100, 101, 102],
        "volume": [1000, 1100, 1200, 1300, 1400],
    })
    
    indicators = {}
    
    # This should trigger regime detection
    ensemble.consolidate_signals(df, indicators)
    
    # Regime should be detected (bull in this case)
    assert ensemble.regime is not None


def test_weight_store_history(weight_store: MetaWeightStore, sample_strategies):
    """Test weight history retrieval."""
    # Save weights for multiple dates
    for days_ago in [0, 7, 14]:
        date = (datetime.utcnow() - timedelta(days=days_ago)).date().isoformat()
        weights = {name: 0.33 + (days_ago * 0.01) for name in sample_strategies}
        metrics = {name: {"sharpe": 1.5} for name in sample_strategies}
        weight_store.save(regime="bull", weights=weights, metrics=metrics, snapshot_date=date)
    
    # Get history
    history = weight_store.get_history(regime="bull", days=30)
    
    assert len(history) >= 3  # Should have at least 3 snapshots
    
    # Check that history is sorted by date (newest first)
    dates = [h["snapshot_date"] for h in history]
    assert dates == sorted(dates, reverse=True)

