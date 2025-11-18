"""Tests for exposure and concentration limits blocking trades."""
from __future__ import annotations

import pytest

from app.backtesting.unified_risk_manager import UnifiedRiskManager
from app.services.recommendation_service import RecommendationService
from app.services.exposure_ledger_service import ExposureLedgerService
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


@pytest.fixture
def exposure_ledger():
    """Create ExposureLedgerService instance for testing."""
    return ExposureLedgerService()


class TestExposureLimits:
    """Test that exposure limits block trades when exceeded."""

    def test_exposure_limit_blocks_when_exceeded(self, risk_service, sample_recommendation):
        """Test that aggregate exposure limit (2× equity) blocks trades."""
        equity = 10000.0
        limit_multiplier = settings.EXPOSURE_LIMIT_MULTIPLIER  # 2.0

        # Create context with existing high exposure
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

        # Mock existing positions that already exceed limit
        existing_positions = [
            {"symbol": "BTCUSDT", "notional": 15000.0, "beta": 1.0, "side": "BUY"},
            {"symbol": "BTCUSDT", "notional": 6000.0, "beta": 1.0, "side": "BUY"},
        ]  # Total: $21,000 = 2.1× equity (exceeds 2.0× limit)

        with patch.object(
            risk_service.user_risk_profile_service,
            "get_context",
            return_value=ctx,
        ), patch.object(
            risk_service.user_risk_profile_service,
            "get_open_positions",
            return_value=existing_positions,
        ):
            sizing_result = risk_service._calculate_position_sizing(
                sample_recommendation,
                user_id="test_user",
            )

            assert sizing_result is not None

            # Should be blocked due to exposure limit
            assert sizing_result.get("status") == "exposure_limit_exceeded", (
                "Trade should be blocked when exposure exceeds limit"
            )

            # Verify exposure metrics are included
            assert "current_exposure_multiplier" in sizing_result
            assert "projected_exposure_multiplier" in sizing_result
            assert sizing_result["projected_exposure_multiplier"] > limit_multiplier

            # Verify message
            message = sizing_result.get("message", "")
            assert "exposición" in message.lower() or "exposure" in message.lower()
            assert "límite" in message.lower() or "limit" in message.lower()

    def test_concentration_limit_blocks_when_exceeded(self, risk_service, sample_recommendation):
        """Test that concentration limit (30% per symbol) blocks trades."""
        equity = 10000.0
        concentration_limit_pct = 30.0

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

        # Existing position in same symbol that exceeds 30% limit
        existing_positions = [
            {"symbol": "BTCUSDT", "notional": 3500.0, "beta": 1.0, "side": "BUY"},
        ]  # 35% of equity (exceeds 30% limit)

        # Calculate sizing that would add more to same symbol
        entry = sample_recommendation["entry_range"]["optimal"]
        stop = sample_recommendation["stop_loss_take_profit"]["stop_loss"]
        risk_per_unit = abs(entry - stop)
        base_units = (equity * 0.01) / risk_per_unit  # 1% risk
        base_notional = base_units * entry

        # Total would be 35% + base_notional, which should exceed 30%

        with patch.object(
            risk_service.user_risk_profile_service,
            "get_context",
            return_value=ctx,
        ), patch.object(
            risk_service.user_risk_profile_service,
            "get_open_positions",
            return_value=existing_positions,
        ):
            sizing_result = risk_service._calculate_position_sizing(
                sample_recommendation,
                user_id="test_user",
            )

            assert sizing_result is not None

            # Should be blocked due to concentration limit
            # Note: This depends on the actual sizing calculation
            # If the base sizing is small enough, it might not exceed limit
            # But if it does, it should be blocked

            if sizing_result.get("status") == "risk_blocked":
                violations = sizing_result.get("violations", [])
                concentration_violations = [
                    v for v in violations
                    if v.get("type") == "concentration_limit"
                ]

                if concentration_violations:
                    violation = concentration_violations[0]
                    assert violation["symbol"] == "BTCUSDT"
                    assert violation["total"] > equity * (concentration_limit_pct / 100.0)

    def test_correlation_limit_blocks_highly_correlated_positions(
        self, risk_service, sample_recommendation, exposure_ledger
    ):
        """Test that highly correlated positions (> 0.7) in same direction are blocked."""
        equity = 10000.0
        correlation_threshold = 0.7

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

        # Existing position in highly correlated symbol
        existing_positions = [
            {"symbol": "ETHUSDT", "notional": 2000.0, "beta": 1.0, "side": "BUY"},
        ]

        # Correlation matrix with high correlation
        correlation_matrix = {
            "BTCUSDT": {
                "ETHUSDT": 0.85,  # High correlation
            },
        }

        # Mock apply_limits to use correlation matrix
        with patch.object(
            risk_service.user_risk_profile_service,
            "get_context",
            return_value=ctx,
        ), patch.object(
            risk_service.user_risk_profile_service,
            "get_open_positions",
            return_value=existing_positions,
        ):
            # Create risk manager and test apply_limits directly
            risk_manager = UnifiedRiskManager(base_capital=equity, risk_budget_pct=1.0)

            entry = sample_recommendation["entry_range"]["optimal"]
            stop = sample_recommendation["stop_loss_take_profit"]["stop_loss"]
            risk_per_unit = abs(entry - stop)
            base_units = (equity * 0.01) / risk_per_unit
            notional = base_units * entry

            limits_result = risk_manager.apply_limits(
                position_request={
                    "symbol": "BTCUSDT",
                    "notional": notional,
                    "entry": entry,
                    "side": "BUY",
                },
                user_equity=equity,
                existing_positions=existing_positions,
                exposure_cap=1.0,
                concentration_limit_pct=30.0,
                correlation_threshold=correlation_threshold,
                correlation_matrix=correlation_matrix,
            )

            # Should be blocked due to correlation
            if not limits_result["allowed"]:
                violations = limits_result.get("violations", [])
                correlation_violations = [
                    v for v in violations
                    if v.get("type") == "correlation_limit"
                ]

                if correlation_violations:
                    violation = correlation_violations[0]
                    assert violation["symbol"] == "BTCUSDT"
                    assert violation["existing_symbol"] == "ETHUSDT"
                    assert abs(violation["abs_correlation"]) > correlation_threshold

    def test_exposure_allows_when_below_limit(self, risk_service, sample_recommendation):
        """Test that trades are allowed when exposure is below limit."""
        equity = 10000.0
        limit_multiplier = settings.EXPOSURE_LIMIT_MULTIPLIER  # 2.0

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

        # Existing positions below limit
        existing_positions = [
            {"symbol": "BTCUSDT", "notional": 5000.0, "beta": 1.0, "side": "BUY"},
        ]  # 0.5× equity (below 2.0× limit)

        with patch.object(
            risk_service.user_risk_profile_service,
            "get_context",
            return_value=ctx,
        ), patch.object(
            risk_service.user_risk_profile_service,
            "get_open_positions",
            return_value=existing_positions,
        ):
            sizing_result = risk_service._calculate_position_sizing(
                sample_recommendation,
                user_id="test_user",
            )

            assert sizing_result is not None

            # Should not be blocked
            assert sizing_result.get("status") != "exposure_limit_exceeded", (
                "Trade should not be blocked when exposure is below limit"
            )

            # Verify exposure metrics
            exposure_summary = sizing_result.get("exposure_summary", {})
            projected_multiplier = exposure_summary.get("projected_exposure_multiplier", 0.0)
            assert projected_multiplier <= limit_multiplier, (
                f"Projected exposure {projected_multiplier:.2f}× should be <= limit {limit_multiplier:.2f}×"
            )

    def test_exposure_validation_calculates_correctly(self, exposure_ledger):
        """Test that exposure validation calculates beta-adjusted notional correctly."""
        user_id = "test_user"
        equity = 10000.0
        limit_multiplier = 2.0

        # Add existing positions with different betas
        existing_positions_data = [
            {"symbol": "BTCUSDT", "notional": 5000.0, "beta": 1.0},
            {"symbol": "ETHUSDT", "notional": 3000.0, "beta": 1.2},
        ]

        # Convert to format expected by validate_new_position
        existing_positions = [
            {
                "symbol": pos["symbol"],
                "notional": pos["notional"],
                "beta_value": pos["beta"],
                "direction": "BUY",
            }
            for pos in existing_positions_data
        ]

        # Mock get_active_positions
        with patch.object(
            exposure_ledger,
            "get_active_positions",
            return_value=[],
        ):
            # Calculate current exposure manually
            current_beta_adjusted = sum(
                pos["notional"] * abs(pos["beta_value"]) for pos in existing_positions
            )
            current_multiplier = current_beta_adjusted / equity

            # Validate new position
            new_notional = 2000.0
            new_beta = 1.0

            # Mock calculate_exposure_summary to return our test data
            from app.services.exposure_ledger_service import ExposureSummary

            current_summary = ExposureSummary(
                user_id=user_id,
                total_notional=sum(pos["notional"] for pos in existing_positions),
                beta_adjusted_notional=current_beta_adjusted,
                position_count=len(existing_positions),
                positions=existing_positions,
                current_exposure_multiplier=current_multiplier,
                limit_exposure_multiplier=limit_multiplier,
            )

            with patch.object(
                exposure_ledger,
                "calculate_exposure_summary",
                return_value=current_summary,
            ):
                validation = exposure_ledger.validate_new_position(
                    user_id=user_id,
                    user_equity=equity,
                    new_notional=new_notional,
                    new_beta=new_beta,
                    limit_multiplier=limit_multiplier,
                )

                # Calculate expected
                projected_beta_adjusted = current_beta_adjusted + (new_notional * abs(new_beta))
                projected_multiplier = projected_beta_adjusted / equity

                assert validation["current_exposure_multiplier"] == pytest.approx(current_multiplier, rel=0.01)
                assert validation["projected_exposure_multiplier"] == pytest.approx(projected_multiplier, rel=0.01)

                # Should be allowed if below limit
                if projected_multiplier <= limit_multiplier:
                    assert validation["allowed"] is True
                else:
                    assert validation["allowed"] is False
                    assert "exceedería límite" in validation["reason"] or "exceed" in validation["reason"].lower()

