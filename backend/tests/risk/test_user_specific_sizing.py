"""Tests for user-specific position sizing with different equity/drawdown scenarios."""
from __future__ import annotations

import pytest

from app.backtesting.unified_risk_manager import UnifiedRiskManager
from app.services.recommendation_service import RecommendationService
from app.services.user_risk_profile_service import UserRiskProfileService, UserRiskContext
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


class TestUserSpecificSizing:
    """Test that sizing changes proportionally with different equity/drawdown scenarios."""

    def test_sizing_proportional_to_equity(self, risk_service, sample_recommendation):
        """Test that sizing scales proportionally with equity."""
        # Test with different equity levels
        test_cases = [
            {"equity": 1000.0, "expected_min_units": 0.0005},  # $1k -> ~0.0005 BTC
            {"equity": 5000.0, "expected_min_units": 0.0025},  # $5k -> ~0.0025 BTC
            {"equity": 10000.0, "expected_min_units": 0.005},  # $10k -> ~0.005 BTC
            {"equity": 50000.0, "expected_min_units": 0.025},  # $50k -> ~0.025 BTC
        ]

        entry = sample_recommendation["entry_range"]["optimal"]
        stop = sample_recommendation["stop_loss_take_profit"]["stop_loss"]
        risk_per_unit = abs(entry - stop)  # $2,000

        for case in test_cases:
            equity = case["equity"]
            expected_min = case["expected_min_units"]

            # Create mock user context
            ctx = UserRiskContext(
                user_id="test_user",
                equity=equity,
                drawdown_pct=0.0,
                base_risk_pct=1.0,
                realized_vol=None,
                avg_exposure_pct=0.0,
                total_notional=0.0,
                effective_leverage=1.0,
                open_positions_count=0,
                has_data=True,
            )

            # Mock the user risk profile service
            with patch.object(
                risk_service.user_risk_profile_service,
                "get_context",
                return_value=ctx,
            ):
                sizing_result = risk_service._calculate_position_sizing(
                    sample_recommendation,
                    user_id="test_user",
                )

                assert sizing_result is not None, f"Sizing should not be None for equity {equity}"
                assert "units" in sizing_result, f"Sizing should include units for equity {equity}"

                units = sizing_result["units"]
                notional = sizing_result.get("notional", 0.0)

                # Verify proportional scaling (within 10% tolerance)
                expected_risk = equity * 0.01  # 1% risk
                expected_units = expected_risk / risk_per_unit
                tolerance = expected_units * 0.1

                assert abs(units - expected_units) < tolerance, (
                    f"For equity ${equity:,.0f}, expected ~{expected_units:.6f} units, "
                    f"got {units:.6f} units"
                )

                # Verify notional scales proportionally
                assert notional > 0, f"Notional should be positive for equity {equity}"
                assert abs(notional - (units * entry)) < 1.0, "Notional should equal units * entry"

    def test_sizing_reduces_with_drawdown(self, risk_service, sample_recommendation):
        """Test that sizing reduces as drawdown increases."""
        base_equity = 10000.0
        entry = sample_recommendation["entry_range"]["optimal"]
        stop = sample_recommendation["stop_loss_take_profit"]["stop_loss"]

        # Test with increasing drawdown
        drawdown_cases = [
            {"drawdown": 0.0, "expected_multiplier": 1.0},  # No drawdown = full sizing
            {"drawdown": 10.0, "expected_multiplier": 0.8},  # 10% DD = 80% sizing
            {"drawdown": 25.0, "expected_multiplier": 0.5},  # 25% DD = 50% sizing
            {"drawdown": 40.0, "expected_multiplier": 0.2},  # 40% DD = 20% sizing
        ]

        previous_units = None

        for case in drawdown_cases:
            drawdown = case["drawdown"]
            expected_multiplier = case["expected_multiplier"]

            # Calculate expected equity after drawdown
            peak_equity = base_equity / (1 - drawdown / 100.0) if drawdown > 0 else base_equity
            current_equity = base_equity

            ctx = UserRiskContext(
                user_id="test_user",
                equity=current_equity,
                drawdown_pct=drawdown,
                base_risk_pct=1.0,
                realized_vol=None,
                avg_exposure_pct=0.0,
                total_notional=0.0,
                effective_leverage=1.0,
                open_positions_count=0,
                has_data=True,
                peak_equity=peak_equity,
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

                assert sizing_result is not None, f"Sizing should not be None for drawdown {drawdown}%"
                assert "units" in sizing_result, f"Sizing should include units for drawdown {drawdown}%"

                units = sizing_result["units"]

                # Calculate base sizing (no drawdown)
                if previous_units is None:
                    base_units = units / expected_multiplier
                    previous_units = units
                else:
                    # Verify sizing decreases with increasing drawdown
                    assert units <= previous_units, (
                        f"Sizing should decrease as drawdown increases. "
                        f"Drawdown {drawdown}% has {units:.6f} units, "
                        f"previous had {previous_units:.6f} units"
                    )
                    previous_units = units

                # Verify exposure multiplier is applied
                exposure_multiplier = sizing_result.get("exposure_multiplier", 1.0)
                tolerance = 0.05  # 5% tolerance

                assert abs(exposure_multiplier - expected_multiplier) < tolerance, (
                    f"For drawdown {drawdown}%, expected exposure multiplier ~{expected_multiplier:.2f}, "
                    f"got {exposure_multiplier:.2f}"
                )

    def test_sizing_with_zero_equity_returns_missing_equity(self, risk_service, sample_recommendation):
        """Test that sizing returns missing_equity status when equity is zero."""
        ctx = UserRiskContext(
            user_id="test_user",
            equity=0.0,
            drawdown_pct=0.0,
            base_risk_pct=1.0,
            realized_vol=None,
            avg_exposure_pct=0.0,
            total_notional=0.0,
            effective_leverage=1.0,
            open_positions_count=0,
            has_data=False,  # No data
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
            assert sizing_result.get("status") == "missing_equity"
            assert "requires_capital_input" in sizing_result
            assert sizing_result["requires_capital_input"] is True

    def test_sizing_with_high_drawdown_blocks_trade(self, risk_service, sample_recommendation):
        """Test that sizing is blocked when drawdown exceeds maximum."""
        # Drawdown > 50% should result in exposure_multiplier = 0
        ctx = UserRiskContext(
            user_id="test_user",
            equity=5000.0,  # 50% of peak
            drawdown_pct=50.0,
            base_risk_pct=1.0,
            realized_vol=None,
            avg_exposure_pct=0.0,
            total_notional=0.0,
            effective_leverage=1.0,
            open_positions_count=0,
            has_data=True,
            peak_equity=10000.0,
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

            # At 50% drawdown, exposure_multiplier should be 0, which may block sizing
            # or result in very small sizing
            assert sizing_result is not None

            exposure_multiplier = sizing_result.get("exposure_multiplier", 1.0)
            assert exposure_multiplier <= 0.01, (
                f"At 50% drawdown, exposure multiplier should be near 0, got {exposure_multiplier:.2f}"
            )

    def test_sizing_scales_with_risk_budget(self, risk_service, sample_recommendation):
        """Test that sizing scales with risk budget percentage."""
        equity = 10000.0
        risk_budgets = [0.5, 1.0, 1.5, 2.0]  # 0.5%, 1%, 1.5%, 2%

        entry = sample_recommendation["entry_range"]["optimal"]
        stop = sample_recommendation["stop_loss_take_profit"]["stop_loss"]
        risk_per_unit = abs(entry - stop)

        previous_units = None

        for risk_budget in risk_budgets:
            ctx = UserRiskContext(
                user_id="test_user",
                equity=equity,
                drawdown_pct=0.0,
                base_risk_pct=risk_budget,
                realized_vol=None,
                avg_exposure_pct=0.0,
                total_notional=0.0,
                effective_leverage=1.0,
                open_positions_count=0,
                has_data=True,
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
                units = sizing_result["units"]

                # Verify proportional scaling
                expected_risk = equity * (risk_budget / 100.0)
                expected_units = expected_risk / risk_per_unit
                tolerance = expected_units * 0.1

                assert abs(units - expected_units) < tolerance, (
                    f"For risk budget {risk_budget}%, expected ~{expected_units:.6f} units, "
                    f"got {units:.6f} units"
                )

                # Verify sizing increases with risk budget
                if previous_units is not None:
                    assert units > previous_units, (
                        f"Sizing should increase with risk budget. "
                        f"Risk budget {risk_budget}% has {units:.6f} units, "
                        f"previous had {previous_units:.6f} units"
                    )

                previous_units = units

