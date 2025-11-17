"""Tests for advanced metrics and guardrails."""
import pytest

import numpy as np
import pandas as pd

from app.backtesting.advanced_metrics import MetricsReport, calmar_penalized
from app.backtesting.guardrails import GuardrailChecker, GuardrailConfig
from app.backtesting.ruin_simulation import monte_carlo_ruin


def test_cagr_guardrail_fails_on_short_period():
    """Test that campaigns with unrealistic CAGR on short periods fail."""
    # Simulate unrealistic result: 500% CAGR in 4 days
    cagr = 500.0
    n_days = 4

    # This should be caught by validation, but if it gets through,
    # guardrails should catch it
    config = GuardrailConfig()
    checker = GuardrailChecker(config)

    # Create mock metrics
    metrics = {
        "cagr": cagr,
        "max_drawdown": 10.0,
        "total_trades": 10,
    }

    # Check duration
    result = checker.check_history_length(n_days)
    assert not result.passed, "Should reject campaigns with < 24 months"


def test_ruin_probability_divergence():
    """Test that ruin probability doesn't diverge too much between theoretical and realistic."""
    # Generate sample returns
    np.random.seed(42)
    returns_theoretical = np.random.normal(0.001, 0.02, 100)  # 0.1% mean, 2% std
    returns_realistic = returns_theoretical * 0.95  # 5% worse due to frictions

    # Simulate ruin for both
    result_theoretical = monte_carlo_ruin(
        returns_theoretical,
        equity=10000.0,
        n_paths=1000,
        seed=42,
    )

    result_realistic = monte_carlo_ruin(
        returns_realistic,
        equity=10000.0,
        n_paths=1000,
        seed=42,
    )

    # Calculate divergence
    divergence = abs(result_realistic.ruin_probability - result_theoretical.ruin_probability)

    # Divergence should be reasonable (< 10% absolute difference)
    assert divergence < 0.10, f"Ruin probability divergence too high: {divergence}"


def test_calmar_penalized():
    """Test penalized Calmar calculation."""
    calmar = 2.0
    longest_drawdown_days = 30
    total_days = 365

    penalized = calmar_penalized(calmar, longest_drawdown_days, total_days)

    # Should be penalized
    expected_penalty = 30 / 365
    expected_calmar = calmar * (1 - expected_penalty)
    assert abs(penalized - expected_calmar) < 0.01


def test_metrics_report_bootstrap():
    """Test that bootstrap confidence intervals are calculated."""
    np.random.seed(42)
    returns = pd.Series(np.random.normal(0.001, 0.02, 252))  # 1 year of daily returns

    report = MetricsReport.from_returns(
        returns,
        bootstrap_trials=1000,
        seed=42,
    )

    # Should have confidence intervals
    assert "cagr" in report.confidence_intervals
    assert "sharpe" in report.confidence_intervals
    assert "calmar" in report.confidence_intervals

    # Check percentiles are ordered
    cagr_ci = report.confidence_intervals["cagr"]
    assert cagr_ci["p5"] <= cagr_ci["p50"] <= cagr_ci["p95"]


def test_ruin_simulation_reproducibility():
    """Test that ruin simulation is reproducible with same seed."""
    returns = pd.Series([0.01, -0.02, 0.015, -0.01, 0.02] * 20)

    result1 = monte_carlo_ruin(returns, equity=10000.0, n_paths=1000, seed=42)
    result2 = monte_carlo_ruin(returns, equity=10000.0, n_paths=1000, seed=42)

    # Should be identical
    assert abs(result1.ruin_probability - result2.ruin_probability) < 0.001
    if result1.distribution and result2.distribution:
        assert np.allclose(result1.distribution, result2.distribution)


def test_guardrail_calmar_oos():
    """Test guardrail rejects low OOS Calmar."""
    checker = GuardrailChecker()

    result = checker.check_calmar_oos(1.0)  # Below threshold of 1.5
    assert not result.passed
    assert result.reason.value == "calmar_oos_too_low"

    result = checker.check_calmar_oos(2.0)  # Above threshold
    assert result.passed


def test_guardrail_max_drawdown():
    """Test guardrail rejects high drawdown."""
    checker = GuardrailChecker()

    result = checker.check_max_drawdown(30.0)  # 30% > 25% threshold
    assert not result.passed

    result = checker.check_max_drawdown(20.0)  # 20% < 25% threshold
    assert result.passed


def test_guardrail_risk_of_ruin():
    """Test guardrail rejects high risk of ruin."""
    checker = GuardrailChecker()

    result = checker.check_risk_of_ruin(0.10)  # 10% > 5% threshold
    assert not result.passed

    result = checker.check_risk_of_ruin(0.03)  # 3% < 5% threshold
    assert result.passed


def test_guardrail_calmar_ci_stability():
    """Test guardrail rejects unstable Calmar (low CI lower bound)."""
    checker = GuardrailChecker()

    result = checker.check_calmar_ci_stability(0.5)  # Below threshold of 1.0
    assert not result.passed
    assert result.reason.value == "unstable_calmar_ci"

    result = checker.check_calmar_ci_stability(1.5)  # Above threshold
    assert result.passed


def test_metrics_report_from_returns():
    """Test MetricsReport creation from returns."""
    np.random.seed(42)
    returns = pd.Series(np.random.normal(0.001, 0.02, 100))

    equity_curve = [10000.0]
    for ret in returns:
        equity_curve.append(equity_curve[-1] * (1 + ret))

    report = MetricsReport.from_returns(
        returns,
        equity_curve=equity_curve,
        initial_capital=10000.0,
        total_days=100,
    )

    # Should have all metrics
    assert "cagr" in report.metrics
    assert "sharpe" in report.metrics
    assert "sortino" in report.metrics
    assert "calmar" in report.metrics
    assert "calmar_penalized" in report.metrics
    assert "ulcer_index" in report.metrics
    assert "drawdown_recovery" in report.metrics


def test_integration_guardrails_reject_unrealistic_campaign():
    """Integration test: guardrails should reject unrealistic campaigns."""
    from app.backtesting.guardrails import GuardrailChecker, GuardrailConfig
    from app.backtesting.validation import CampaignValidator

    # Simulate unrealistic campaign: 500% CAGR in 4 days
    validator = CampaignValidator(min_days=730)
    start_date = pd.Timestamp("2020-01-01")
    end_date = pd.Timestamp("2020-01-05")  # Only 4 days

    # Should fail validation
    result = validator.validate_window(start_date, end_date)
    assert not result.passed, "Should reject campaigns with < 730 days"

    # If it somehow gets through, guardrails should catch it
    checker = GuardrailChecker(GuardrailConfig(min_months=24))
    duration_days = 4
    result = checker.check_history_length(duration_days)
    assert not result.passed, "Should reject campaigns with < 24 months"


def test_ruin_probability_theoretical_vs_realistic():
    """Test that ruin probability divergence is detected."""
    # Generate returns
    np.random.seed(42)
    returns_base = np.random.normal(0.001, 0.02, 100)
    
    # Theoretical: no frictions
    returns_theoretical = pd.Series(returns_base)
    
    # Realistic: 5% worse due to frictions
    returns_realistic = pd.Series(returns_base * 0.95)

    # Simulate ruin
    result_theoretical = monte_carlo_ruin(
        returns_theoretical,
        equity=10000.0,
        n_paths=1000,
        seed=42,
    )

    result_realistic = monte_carlo_ruin(
        returns_realistic,
        equity=10000.0,
        n_paths=1000,
        seed=42,
    )

    # Divergence should be reasonable
    divergence = abs(result_realistic.ruin_probability - result_theoretical.ruin_probability)
    
    # Should not diverge more than 10% absolute
    assert divergence < 0.10, f"Ruin probability divergence too high: {divergence}"
    
    # Realistic should have higher ruin probability (worse performance)
    assert result_realistic.ruin_probability >= result_theoretical.ruin_probability

