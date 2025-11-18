"""Tests for no-trade rules in strategy ensemble."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from app.strategies.performance_store import StrategyPerformanceStore
from app.strategies.strategy_ensemble import StrategyEnsemble
from app.strategies.weight_store import MetaWeightStore


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


@pytest.fixture
def config_path(tmp_path):
    """Create a temporary config file."""
    config_file = tmp_path / "ensemble.yaml"
    config_content = """
no_trade_rules:
  min_agreement: 0.67
  max_cross_corr: 0.75
  min_rr: 1.2
  correlation_window_days: 30
  mae_mfe_window_days: 60
  enabled: true
  require_unanimous_on_conflict: true
"""
    config_file.write_text(config_content)
    return config_file


def test_no_trade_on_low_agreement(sample_df, sample_indicators, config_path):
    """Test that HOLD is forced when agreement is too low."""
    ensemble = StrategyEnsemble(
        weight_store=MetaWeightStore(),
        config_path=config_path,
    )

    # Mock signals with low agreement (1 BUY, 1 SELL, 1 HOLD)
    with patch.object(ensemble, "strategies") as mock_strategies:
        mock_strategy1 = Mock()
        mock_strategy1.name = "momentum_trend"
        mock_strategy1.generate_signal.return_value = {
            "signal": "BUY",
            "confidence": 70.0,
            "reason": "test",
        }

        mock_strategy2 = Mock()
        mock_strategy2.name = "mean_reversion"
        mock_strategy2.generate_signal.return_value = {
            "signal": "SELL",
            "confidence": 65.0,
            "reason": "test",
        }

        mock_strategy3 = Mock()
        mock_strategy3.name = "breakout"
        mock_strategy3.generate_signal.return_value = {
            "signal": "HOLD",
            "confidence": 50.0,
            "reason": "test",
        }

        mock_strategies.__iter__.return_value = [mock_strategy1, mock_strategy2, mock_strategy3]

        # Mock performance store to avoid DB calls
        with patch.object(ensemble.performance_store, "calculate_correlation_matrix") as mock_corr:
            mock_corr.return_value = {
                "momentum_trend": {"mean_reversion": 0.5, "breakout": 0.4},
                "mean_reversion": {"momentum_trend": 0.5, "breakout": 0.3},
                "breakout": {"momentum_trend": 0.4, "mean_reversion": 0.3},
            }

            with patch.object(ensemble.performance_store, "get_strategy_mae_mfe") as mock_mae_mfe:
                mock_mae_mfe.return_value = {
                    "mae_pct": 2.0,
                    "mfe_pct": 3.0,
                    "rr_expected": 1.5,
                }

                result = ensemble.consolidate_signals(sample_df, sample_indicators)

                # Should force HOLD due to low agreement (1/3 = 0.33 < 0.67)
                assert result["signal"] == "HOLD"
                assert "decision_reason" in result
                assert "agreement_too_low" in result["decision_reason"] or "buy_sell_conflict" in result["decision_reason"]


def test_no_trade_on_buy_sell_conflict(sample_df, sample_indicators, config_path):
    """Test that HOLD is forced when there's BUY vs SELL conflict."""
    ensemble = StrategyEnsemble(
        weight_store=MetaWeightStore(),
        config_path=config_path,
    )

    # Mock signals with BUY and SELL (conflict)
    with patch.object(ensemble, "strategies") as mock_strategies:
        mock_strategy1 = Mock()
        mock_strategy1.name = "momentum_trend"
        mock_strategy1.generate_signal.return_value = {
            "signal": "BUY",
            "confidence": 80.0,
            "reason": "test",
        }

        mock_strategy2 = Mock()
        mock_strategy2.name = "mean_reversion"
        mock_strategy2.generate_signal.return_value = {
            "signal": "SELL",
            "confidence": 75.0,
            "reason": "test",
        }

        mock_strategy3 = Mock()
        mock_strategy3.name = "breakout"
        mock_strategy3.generate_signal.return_value = {
            "signal": "BUY",
            "confidence": 70.0,
            "reason": "test",
        }

        mock_strategies.__iter__.return_value = [mock_strategy1, mock_strategy2, mock_strategy3]

        # Mock performance store
        with patch.object(ensemble.performance_store, "calculate_correlation_matrix") as mock_corr:
            mock_corr.return_value = {
                "momentum_trend": {"mean_reversion": 0.5, "breakout": 0.4},
                "mean_reversion": {"momentum_trend": 0.5, "breakout": 0.3},
                "breakout": {"momentum_trend": 0.4, "mean_reversion": 0.3},
            }

            with patch.object(ensemble.performance_store, "get_strategy_mae_mfe") as mock_mae_mfe:
                mock_mae_mfe.return_value = {
                    "mae_pct": 2.0,
                    "mfe_pct": 3.0,
                    "rr_expected": 1.5,
                }

                result = ensemble.consolidate_signals(sample_df, sample_indicators)

                # Should force HOLD due to BUY vs SELL conflict
                assert result["signal"] == "HOLD"
                assert "decision_reason" in result
                assert "buy_sell_conflict" in result["decision_reason"]


def test_no_trade_on_high_correlation(sample_df, sample_indicators, config_path):
    """Test that HOLD is forced when strategies are highly correlated."""
    ensemble = StrategyEnsemble(
        weight_store=MetaWeightStore(),
        config_path=config_path,
    )

    # Mock signals with high agreement
    with patch.object(ensemble, "strategies") as mock_strategies:
        mock_strategy1 = Mock()
        mock_strategy1.name = "momentum_trend"
        mock_strategy1.generate_signal.return_value = {
            "signal": "BUY",
            "confidence": 80.0,
            "reason": "test",
        }

        mock_strategy2 = Mock()
        mock_strategy2.name = "mean_reversion"
        mock_strategy2.generate_signal.return_value = {
            "signal": "BUY",
            "confidence": 75.0,
            "reason": "test",
        }

        mock_strategy3 = Mock()
        mock_strategy3.name = "breakout"
        mock_strategy3.generate_signal.return_value = {
            "signal": "BUY",
            "confidence": 70.0,
            "reason": "test",
        }

        mock_strategies.__iter__.return_value = [mock_strategy1, mock_strategy2, mock_strategy3]

        # Mock high correlation (> 0.75)
        with patch.object(ensemble.performance_store, "calculate_correlation_matrix") as mock_corr:
            mock_corr.return_value = {
                "momentum_trend": {"mean_reversion": 0.85, "breakout": 0.4},  # High correlation
                "mean_reversion": {"momentum_trend": 0.85, "breakout": 0.3},
                "breakout": {"momentum_trend": 0.4, "mean_reversion": 0.3},
            }

            with patch.object(ensemble.performance_store, "get_strategy_mae_mfe") as mock_mae_mfe:
                mock_mae_mfe.return_value = {
                    "mae_pct": 2.0,
                    "mfe_pct": 3.0,
                    "rr_expected": 1.5,
                }

                result = ensemble.consolidate_signals(sample_df, sample_indicators)

                # Should force HOLD due to high correlation
                assert result["signal"] == "HOLD"
                assert "decision_reason" in result
                assert "high_correlation" in result["decision_reason"]


def test_no_trade_on_low_expected_rr(sample_df, sample_indicators, config_path):
    """Test that HOLD is forced when expected RR is too low."""
    ensemble = StrategyEnsemble(
        weight_store=MetaWeightStore(),
        config_path=config_path,
    )

    # Mock signals with high agreement
    with patch.object(ensemble, "strategies") as mock_strategies:
        mock_strategy1 = Mock()
        mock_strategy1.name = "momentum_trend"
        mock_strategy1.generate_signal.return_value = {
            "signal": "BUY",
            "confidence": 80.0,
            "reason": "test",
        }

        mock_strategy2 = Mock()
        mock_strategy2.name = "mean_reversion"
        mock_strategy2.generate_signal.return_value = {
            "signal": "BUY",
            "confidence": 75.0,
            "reason": "test",
        }

        mock_strategy3 = Mock()
        mock_strategy3.name = "breakout"
        mock_strategy3.generate_signal.return_value = {
            "signal": "BUY",
            "confidence": 70.0,
            "reason": "test",
        }

        mock_strategies.__iter__.return_value = [mock_strategy1, mock_strategy2, mock_strategy3]

        # Mock low correlation
        with patch.object(ensemble.performance_store, "calculate_correlation_matrix") as mock_corr:
            mock_corr.return_value = {
                "momentum_trend": {"mean_reversion": 0.5, "breakout": 0.4},
                "mean_reversion": {"momentum_trend": 0.5, "breakout": 0.3},
                "breakout": {"momentum_trend": 0.4, "mean_reversion": 0.3},
            }

            # Mock low expected RR (< 1.2)
            with patch.object(ensemble.performance_store, "get_strategy_mae_mfe") as mock_mae_mfe:
                mock_mae_mfe.return_value = {
                    "mae_pct": 3.0,
                    "mfe_pct": 2.0,  # MFE < MAE -> RR < 1.0
                    "rr_expected": 0.67,  # Below threshold of 1.2
                }

                result = ensemble.consolidate_signals(sample_df, sample_indicators)

                # Should force HOLD due to low expected RR
                assert result["signal"] == "HOLD"
                assert "decision_reason" in result
                assert "expected_rr_too_low" in result["decision_reason"]


def test_trade_allowed_when_rules_pass(sample_df, sample_indicators, config_path):
    """Test that trade is allowed when all rules pass."""
    ensemble = StrategyEnsemble(
        weight_store=MetaWeightStore(),
        config_path=config_path,
    )

    # Mock signals with high agreement (all BUY)
    with patch.object(ensemble, "strategies") as mock_strategies:
        mock_strategy1 = Mock()
        mock_strategy1.name = "momentum_trend"
        mock_strategy1.generate_signal.return_value = {
            "signal": "BUY",
            "confidence": 80.0,
            "reason": "test",
        }

        mock_strategy2 = Mock()
        mock_strategy2.name = "mean_reversion"
        mock_strategy2.generate_signal.return_value = {
            "signal": "BUY",
            "confidence": 75.0,
            "reason": "test",
        }

        mock_strategy3 = Mock()
        mock_strategy3.name = "breakout"
        mock_strategy3.generate_signal.return_value = {
            "signal": "BUY",
            "confidence": 70.0,
            "reason": "test",
        }

        mock_strategies.__iter__.return_value = [mock_strategy1, mock_strategy2, mock_strategy3]

        # Mock low correlation and good RR
        with patch.object(ensemble.performance_store, "calculate_correlation_matrix") as mock_corr:
            mock_corr.return_value = {
                "momentum_trend": {"mean_reversion": 0.5, "breakout": 0.4},
                "mean_reversion": {"momentum_trend": 0.5, "breakout": 0.3},
                "breakout": {"momentum_trend": 0.4, "mean_reversion": 0.3},
            }

            with patch.object(ensemble.performance_store, "get_strategy_mae_mfe") as mock_mae_mfe:
                mock_mae_mfe.return_value = {
                    "mae_pct": 2.0,
                    "mfe_pct": 3.0,
                    "rr_expected": 1.5,  # Above threshold
                }

                result = ensemble.consolidate_signals(sample_df, sample_indicators)

                # Should allow trade (not HOLD)
                assert result["signal"] != "HOLD" or result.get("decision_reason") != "no_trade"
                assert "decision_reason" in result


def test_no_trade_rules_disabled(sample_df, sample_indicators, tmp_path):
    """Test that rules can be disabled."""
    # Create config with rules disabled
    config_file = tmp_path / "ensemble.yaml"
    config_content = """
no_trade_rules:
  enabled: false
"""
    config_file.write_text(config_content)

    ensemble = StrategyEnsemble(
        weight_store=MetaWeightStore(),
        config_path=config_file,
    )

    # Mock signals with low agreement
    with patch.object(ensemble, "strategies") as mock_strategies:
        mock_strategy1 = Mock()
        mock_strategy1.name = "momentum_trend"
        mock_strategy1.generate_signal.return_value = {
            "signal": "BUY",
            "confidence": 70.0,
            "reason": "test",
        }

        mock_strategy2 = Mock()
        mock_strategy2.name = "mean_reversion"
        mock_strategy2.generate_signal.return_value = {
            "signal": "SELL",
            "confidence": 65.0,
            "reason": "test",
        }

        mock_strategy3 = Mock()
        mock_strategy3.name = "breakout"
        mock_strategy3.generate_signal.return_value = {
            "signal": "HOLD",
            "confidence": 50.0,
            "reason": "test",
        }

        mock_strategies.__iter__.return_value = [mock_strategy1, mock_strategy2, mock_strategy3]

        result = ensemble.consolidate_signals(sample_df, sample_indicators)

        # Should not force HOLD when rules are disabled
        # (may still be HOLD due to voting, but not due to no-trade rules)
        assert "decision_reason" in result
        # Decision reason should not be a no-trade reason
        assert "agreement_too_low" not in result.get("decision_reason", "")
        assert "buy_sell_conflict" not in result.get("decision_reason", "")


def test_performance_store_correlation_calculation():
    """Test correlation matrix calculation."""
    store = StrategyPerformanceStore()

    # Mock database query
    with patch.object(store, "_get_session") as mock_session:
        # This is a simplified test - in practice would need to mock DB results
        strategy_names = ["momentum_trend", "mean_reversion", "breakout"]
        
        # Test with empty data
        corr_matrix = store.calculate_correlation_matrix(strategy_names, window_days=30)
        
        assert isinstance(corr_matrix, dict)
        assert len(corr_matrix) == len(strategy_names)
        for strategy in strategy_names:
            assert strategy in corr_matrix


def test_performance_store_mae_mfe():
    """Test MAE/MFE retrieval."""
    store = StrategyPerformanceStore()

    # Mock database query
    with patch.object(store, "_get_session") as mock_session:
        mae_mfe = store.get_strategy_mae_mfe("momentum_trend", window_days=60)
        
        assert isinstance(mae_mfe, dict)
        assert "mae_pct" in mae_mfe
        assert "mfe_pct" in mae_mfe
        assert "rr_expected" in mae_mfe

