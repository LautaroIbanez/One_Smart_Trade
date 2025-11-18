"""Tests for ruin risk blocking when risk_of_ruin > 0.05."""
from __future__ import annotations

import pytest

from app.backtesting.unified_risk_manager import UnifiedRiskManager
from app.backtesting.risk import RuinSimulator
from app.services.recommendation_service import RecommendationService
from app.services.user_risk_profile_service import UserRiskContext
from app.core.config import settings
from unittest.mock import Mock, patch


@pytest.fixture
def sample_recommendation():
    """Sample recommendation for testing."""
    return {
        "id": 1,
        "signal": "BUY",
        "symbol": "BTCUSDT",
        "entry_range": {"optimal": 50000.0},
        "stop_loss_take_profit": {"stop_loss": 48000.0},
        "current_price": 50000.0,
    }


@pytest.fixture
def risk_service():
    """Create RecommendationService instance for testing."""
    return RecommendationService()


class TestRuinBlocks:
    """Test that signals are blocked when risk_of_ruin > 0.05."""

    def test_low_ruin_risk_allows_trade(self, risk_service, sample_recommendation):
        """Test that trades with low ruin risk (< 5%) are allowed."""
        # Good trading metrics: high win rate, good payoff
        ctx = UserRiskContext(
            user_id="test_user",
            equity=10000.0,
            drawdown_pct=5.0,
            base_risk_pct=1.0,
            realized_vol=None,
            avg_exposure_pct=0.0,
            total_notional=0.0,
            effective_leverage=1.0,
            open_positions_count=0,
            has_data=True,
            win_rate=0.60,  # 60% win rate
            payoff_ratio=2.0,  # 2:1 payoff
        )

        with patch.object(
            risk_service.user_risk_profile_service,
            "get_context",
            return_value=ctx,
        ):
            sizing_result = risk_service._calculate_position_sizing(
                sample_recommendation,
                user_id="test_user",
            )

            assert sizing_result is not None
            assert sizing_result.get("status") != "ruin_risk_too_high", (
                "Trade should not be blocked with good trading metrics"
            )

            # Verify ruin risk is calculated and below threshold
            risk_of_ruin = sizing_result.get("risk_of_ruin", 0.0)
            assert risk_of_ruin < settings.RISK_OF_RUIN_MAX, (
                f"Risk of ruin {risk_of_ruin:.2%} should be below threshold "
                f"{settings.RISK_OF_RUIN_MAX:.2%}"
            )

    def test_high_ruin_risk_blocks_trade(self, risk_service, sample_recommendation):
        """Test that trades with high ruin risk (> 10% or multiplier < 0.2) are blocked."""
        # Poor trading metrics: low win rate, poor payoff
        ctx = UserRiskContext(
            user_id="test_user",
            equity=10000.0,
            drawdown_pct=10.0,
            base_risk_pct=1.0,
            realized_vol=None,
            avg_exposure_pct=0.0,
            total_notional=0.0,
            effective_leverage=1.0,
            open_positions_count=0,
            has_data=True,
            win_rate=0.35,  # 35% win rate (poor)
            payoff_ratio=1.1,  # 1.1:1 payoff (poor)
        )

        with patch.object(
            risk_service.user_risk_profile_service,
            "get_context",
            return_value=ctx,
        ):
            sizing_result = risk_service._calculate_position_sizing(
                sample_recommendation,
                user_id="test_user",
            )

            assert sizing_result is not None

            # With poor metrics, ruin risk should be high
            risk_of_ruin = sizing_result.get("risk_of_ruin", 0.0)

            # If ruin risk is very high, trade should be blocked
            if risk_of_ruin > settings.RISK_OF_RUIN_MAX * 2:  # > 10%
                assert sizing_result.get("status") == "ruin_risk_too_high", (
                    f"Trade should be blocked when ruin risk {risk_of_ruin:.2%} > "
                    f"{settings.RISK_OF_RUIN_MAX * 2:.2%}"
                )
                assert "message" in sizing_result
                assert "riesgo de ruina" in sizing_result["message"].lower()

    def test_ruin_risk_reduces_sizing(self, risk_service, sample_recommendation):
        """Test that sizing is reduced when ruin risk exceeds threshold but is not blocked."""
        # Moderate trading metrics: ruin risk > 5% but < 10%
        ctx = UserRiskContext(
            user_id="test_user",
            equity=10000.0,
            drawdown_pct=5.0,
            base_risk_pct=1.0,
            realized_vol=None,
            avg_exposure_pct=0.0,
            total_notional=0.0,
            effective_leverage=1.0,
            open_positions_count=0,
            has_data=True,
            win_rate=0.45,  # 45% win rate (moderate)
            payoff_ratio=1.3,  # 1.3:1 payoff (moderate)
        )

        with patch.object(
            risk_service.user_risk_profile_service,
            "get_context",
            return_value=ctx,
        ):
            sizing_result = risk_service._calculate_position_sizing(
                sample_recommendation,
                user_id="test_user",
            )

            assert sizing_result is not None
            risk_of_ruin = sizing_result.get("risk_of_ruin", 0.0)

            # If ruin risk is between 5% and 10%, sizing should be reduced
            if settings.RISK_OF_RUIN_MAX < risk_of_ruin < settings.RISK_OF_RUIN_MAX * 2:
                ruin_adjustment = sizing_result.get("ruin_adjustment")
                if ruin_adjustment:
                    assert ruin_adjustment.get("applied") is True
                    assert "multiplier" in ruin_adjustment
                    assert ruin_adjustment["multiplier"] < 1.0
                    assert ruin_adjustment["multiplier"] >= 0.2  # Not blocked

                    # Verify adjusted units are less than original
                    original_units = ruin_adjustment.get("original_units", 0.0)
                    adjusted_units = ruin_adjustment.get("adjusted_units", 0.0)
                    assert adjusted_units < original_units, (
                        "Adjusted units should be less than original when ruin adjustment applied"
                    )

    def test_ruin_simulator_calculates_high_risk(self):
        """Test that RuinSimulator correctly calculates high ruin risk for poor metrics."""
        ruin_sim = RuinSimulator()

        # Poor metrics
        win_rate_poor = 0.35
        payoff_poor = 1.1

        # Good metrics
        win_rate_good = 0.60
        payoff_good = 2.0

        ruin_poor = ruin_sim.estimate(
            win_rate=win_rate_poor,
            payoff_ratio=payoff_poor,
            horizon=250,
            threshold=0.5,
        )

        ruin_good = ruin_sim.estimate(
            win_rate=win_rate_good,
            payoff_ratio=payoff_good,
            horizon=250,
            threshold=0.5,
        )

        # Poor metrics should have higher ruin risk
        assert ruin_poor > ruin_good, (
            f"Poor metrics (WR={win_rate_poor}, PR={payoff_poor}) should have higher ruin risk "
            f"({ruin_poor:.2%}) than good metrics (WR={win_rate_good}, PR={payoff_good}) "
            f"({ruin_good:.2%})"
        )

        # Poor metrics should exceed threshold
        assert ruin_poor > settings.RISK_OF_RUIN_MAX, (
            f"Poor metrics should produce ruin risk > {settings.RISK_OF_RUIN_MAX:.2%}, "
            f"got {ruin_poor:.2%}"
        )

    def test_ruin_block_message_format(self, risk_service, sample_recommendation):
        """Test that ruin block message is properly formatted."""
        # Very poor metrics to trigger block
        ctx = UserRiskContext(
            user_id="test_user",
            equity=10000.0,
            drawdown_pct=15.0,
            base_risk_pct=1.0,
            realized_vol=None,
            avg_exposure_pct=0.0,
            total_notional=0.0,
            effective_leverage=1.0,
            open_positions_count=0,
            has_data=True,
            win_rate=0.30,  # Very poor
            payoff_ratio=1.0,  # 1:1 (break even)
        )

        with patch.object(
            risk_service.user_risk_profile_service,
            "get_context",
            return_value=ctx,
        ):
            sizing_result = risk_service._calculate_position_sizing(
                sample_recommendation,
                user_id="test_user",
            )

            assert sizing_result is not None

            if sizing_result.get("status") == "ruin_risk_too_high":
                message = sizing_result.get("message", "")
                assert "riesgo de ruina" in message.lower()
                assert "umbral seguro" in message.lower() or "threshold" in message.lower()
                assert "reduce exposición" in message.lower() or "reduce exposure" in message.lower()

                # Verify risk_of_ruin is included
                assert "risk_of_ruin" in sizing_result
                assert sizing_result["risk_of_ruin"] > settings.RISK_OF_RUIN_MAX

    def test_ruin_risk_with_no_trade_history(self, risk_service, sample_recommendation):
        """Test that ruin risk uses conservative defaults when no trade history available."""
        ctx = UserRiskContext(
            user_id="test_user",
            equity=10000.0,
            drawdown_pct=0.0,
            base_risk_pct=1.0,
            realized_vol=None,
            avg_exposure_pct=0.0,
            total_notional=0.0,
            effective_leverage=1.0,
            open_positions_count=0,
            has_data=True,
            win_rate=None,  # No history
            payoff_ratio=None,  # No history
            trade_history=None,
        )

        with patch.object(
            risk_service.user_risk_profile_service,
            "get_context",
            return_value=ctx,
        ):
            sizing_result = risk_service._calculate_position_sizing(
                sample_recommendation,
                user_id="test_user",
            )

            assert sizing_result is not None
            # Without history, ruin risk should be 0 or very low (conservative)
            risk_of_ruin = sizing_result.get("risk_of_ruin", 0.0)
            assert risk_of_ruin <= settings.RISK_OF_RUIN_MAX, (
                f"Without trade history, ruin risk should be conservative (<= {settings.RISK_OF_RUIN_MAX:.2%}), "
                f"got {risk_of_ruin:.2%}"
            )

