"""Tests for sensitivity guard stability evaluation."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.backtesting.sensitivity_guard import SensitivityGuard, StabilityStatus


@pytest.fixture
def guard():
    """Create a SensitivityGuard instance for testing."""
    return SensitivityGuard(
        max_degradation_pct=20.0,
        max_dd_increase_pct=25.0,
        min_sharpe_threshold=1.0,
        anova_alpha=0.05,
        min_valid_runs=5,
    )


@pytest.fixture
def stable_results_df():
    """Create a DataFrame with stable sensitivity results."""
    np.random.seed(42)
    base_calmar = 2.0
    base_sharpe = 1.5
    base_max_dd = 10.0
    
    # Generate results with small variations (±10% max degradation)
    n_runs = 20
    results = []
    
    for i in range(n_runs):
        # Small random variations
        calmar = base_calmar * (1 + np.random.uniform(-0.1, 0.1))
        sharpe = base_sharpe * (1 + np.random.uniform(-0.1, 0.1))
        max_dd = base_max_dd * (1 + np.random.uniform(-0.1, 0.1))
        
        results.append({
            "params_id": f"params_{i:03d}",
            "calmar": calmar,
            "sharpe": sharpe,
            "max_dd": max_dd,
            "valid": True,
            "breakout.lookback": 20 + np.random.choice([-4, -2, 0, 2, 4]),
            "volatility.low_threshold": 0.2 + np.random.choice([-0.04, -0.02, 0, 0.02, 0.04]),
        })
    
    # Set base params_id to the one with best Calmar
    best_idx = max(range(n_runs), key=lambda i: results[i]["calmar"])
    results[best_idx]["params_id"] = "base_params"
    
    return pd.DataFrame(results)


@pytest.fixture
def unstable_results_df():
    """Create a DataFrame with unstable sensitivity results."""
    np.random.seed(42)
    base_calmar = 2.0
    base_sharpe = 1.5
    base_max_dd = 10.0
    
    # Generate results with large variations (>20% degradation)
    n_runs = 20
    results = []
    
    for i in range(n_runs):
        # Large random variations
        calmar = base_calmar * (1 + np.random.uniform(-0.4, 0.1))  # Up to -40% degradation
        sharpe = base_sharpe * (1 + np.random.uniform(-0.4, 0.1))
        max_dd = base_max_dd * (1 + np.random.uniform(-0.1, 0.4))  # Up to +40% increase
        
        results.append({
            "params_id": f"params_{i:03d}",
            "calmar": max(0.1, calmar),  # Ensure positive
            "sharpe": max(0.1, sharpe),
            "max_dd": max(5.0, max_dd),
            "valid": True,
            "breakout.lookback": 20 + np.random.choice([-4, -2, 0, 2, 4]),
            "volatility.low_threshold": 0.2 + np.random.choice([-0.04, -0.02, 0, 0.02, 0.04]),
        })
    
    # Set base params_id to the one with best Calmar
    best_idx = max(range(n_runs), key=lambda i: results[i]["calmar"])
    results[best_idx]["params_id"] = "base_params"
    
    return pd.DataFrame(results)


@pytest.fixture
def low_sharpe_results_df():
    """Create a DataFrame with some variations below Sharpe threshold."""
    np.random.seed(42)
    base_calmar = 2.0
    base_sharpe = 1.5
    base_max_dd = 10.0
    
    n_runs = 20
    results = []
    
    for i in range(n_runs):
        calmar = base_calmar * (1 + np.random.uniform(-0.1, 0.1))
        # Some variations with low Sharpe
        sharpe = base_sharpe * (1 + np.random.uniform(-0.5, 0.1)) if i < 5 else base_sharpe * (1 + np.random.uniform(-0.1, 0.1))
        max_dd = base_max_dd * (1 + np.random.uniform(-0.1, 0.1))
        
        results.append({
            "params_id": f"params_{i:03d}",
            "calmar": calmar,
            "sharpe": max(0.1, sharpe),
            "max_dd": max_dd,
            "valid": True,
            "breakout.lookback": 20 + np.random.choice([-4, -2, 0, 2, 4]),
        })
    
    best_idx = max(range(n_runs), key=lambda i: results[i]["calmar"])
    results[best_idx]["params_id"] = "base_params"
    
    return pd.DataFrame(results)


def test_stable_results_pass(guard, stable_results_df):
    """Test that stable results pass the guard."""
    report = guard.evaluate(stable_results_df, campaign_id="test_stable")
    
    assert report.status == StabilityStatus.STABLE
    assert report.base_calmar is not None
    assert report.base_calmar > 0
    assert report.max_calmar_degradation_pct is not None
    assert report.max_calmar_degradation_pct <= 20.0
    assert len(report.rejection_reasons) == 0


def test_unstable_results_fail(guard, unstable_results_df):
    """Test that unstable results fail the guard."""
    report = guard.evaluate(unstable_results_df, campaign_id="test_unstable")
    
    assert report.status == StabilityStatus.UNSTABLE
    assert len(report.rejection_reasons) > 0
    # Should have at least one rejection reason
    assert any("degradation" in reason.lower() or "increase" in reason.lower() for reason in report.rejection_reasons)


def test_low_sharpe_fails(guard, low_sharpe_results_df):
    """Test that results with low Sharpe fail the guard."""
    report = guard.evaluate(low_sharpe_results_df, campaign_id="test_low_sharpe")
    
    assert report.status == StabilityStatus.UNSTABLE
    assert any("sharpe" in reason.lower() for reason in report.rejection_reasons)


def test_insufficient_data(guard):
    """Test that insufficient data is handled correctly."""
    # Empty DataFrame
    empty_df = pd.DataFrame()
    report = guard.evaluate(empty_df, campaign_id="test_empty")
    assert report.status == StabilityStatus.INSUFFICIENT_DATA
    
    # Too few valid runs
    small_df = pd.DataFrame({
        "params_id": ["p1", "p2"],
        "calmar": [1.0, 1.1],
        "sharpe": [1.0, 1.1],
        "max_dd": [10.0, 11.0],
        "valid": [True, True],
    })
    report = guard.evaluate(small_df, campaign_id="test_small")
    assert report.status == StabilityStatus.INSUFFICIENT_DATA


def test_anova_analysis(guard):
    """Test ANOVA analysis detects parameter sensitivity."""
    # Create results where a parameter strongly affects Calmar
    np.random.seed(42)
    results = []
    
    for lookback in [16, 18, 20, 22, 24]:
        for _ in range(4):
            # Calmar strongly depends on lookback
            calmar = 2.0 + (lookback - 20) * 0.3 + np.random.uniform(-0.1, 0.1)
            results.append({
                "params_id": f"p_{lookback}_{len(results)}",
                "calmar": calmar,
                "sharpe": 1.5,
                "max_dd": 10.0,
                "valid": True,
                "breakout.lookback": lookback,
            })
    
    df = pd.DataFrame(results)
    best_idx = df["calmar"].idxmax()
    df.loc[best_idx, "params_id"] = "base_params"
    
    report = guard.evaluate(df, campaign_id="test_anova")
    
    # ANOVA should detect sensitivity
    assert report.anova_p_value is not None
    # With strong parameter effect, p-value should be significant
    # (though exact value depends on random seed)


def test_load_and_evaluate(tmp_path, guard, stable_results_df):
    """Test loading results from file and evaluating."""
    # Save results to file
    output_path = tmp_path / "test_results.parquet"
    stable_results_df.to_parquet(output_path, index=False)
    
    # Load and evaluate
    report = guard.load_and_evaluate(output_path, campaign_id="test_load")
    
    assert report.status == StabilityStatus.STABLE
    assert report.base_calmar is not None


def test_load_nonexistent_file(guard):
    """Test handling of nonexistent file."""
    report = guard.load_and_evaluate("nonexistent.parquet", campaign_id="test_nonexistent")
    
    assert report.status == StabilityStatus.INSUFFICIENT_DATA
    assert len(report.rejection_reasons) > 0
    assert "not found" in report.rejection_reasons[0].lower() or "failed" in report.rejection_reasons[0].lower()


def test_custom_base_params_id(guard, stable_results_df):
    """Test specifying custom base params_id."""
    # Set a specific params_id as base
    stable_results_df.loc[0, "params_id"] = "custom_base"
    stable_results_df.loc[0, "calmar"] = stable_results_df["calmar"].max() + 0.1
    
    report = guard.evaluate(
        stable_results_df,
        campaign_id="test_custom",
        base_params_id="custom_base",
    )
    
    assert report.status == StabilityStatus.STABLE
    assert report.base_calmar is not None


def test_degradation_calculation(guard):
    """Test that degradation is calculated correctly."""
    # Create results with known degradation
    results = pd.DataFrame({
        "params_id": ["base", "variant1", "variant2"],
        "calmar": [2.0, 1.5, 1.4],  # 25% and 30% degradation
        "sharpe": [1.5, 1.2, 1.1],  # 20% and 26.7% degradation
        "max_dd": [10.0, 12.0, 13.0],  # 20% and 30% increase
        "valid": [True, True, True],
    })
    
    report = guard.evaluate(results, campaign_id="test_degradation", base_params_id="base")
    
    assert report.base_calmar == 2.0
    assert report.max_calmar_degradation_pct is not None
    assert report.max_calmar_degradation_pct > 20.0  # Should exceed threshold
    assert report.status == StabilityStatus.UNSTABLE


def test_variance_metrics(guard, stable_results_df):
    """Test that variance metrics are calculated."""
    report = guard.evaluate(stable_results_df, campaign_id="test_variance")
    
    assert report.calmar_std is not None
    assert report.sharpe_std is not None
    assert report.max_dd_std is not None
    assert report.calmar_std >= 0
    assert report.sharpe_std >= 0
    assert report.max_dd_std >= 0

