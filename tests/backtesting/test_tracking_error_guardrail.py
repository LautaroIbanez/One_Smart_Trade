"""Tests for tracking error guardrail evaluation."""
import pytest

from app.backtesting.guardrails import GuardrailChecker, GuardrailConfig, CampaignRejectedReason


class TestTrackingErrorGuardrail:
    """Test tracking error guardrail evaluation."""
    
    def test_check_tracking_error_rmse_passes(self):
        """Test that guardrail passes when RMSE is below threshold."""
        config = GuardrailConfig(max_tracking_error_rmse_pct=0.05)  # 5%
        checker = GuardrailChecker(config)
        
        tracking_error_stats = [
            {
                "rmse": 400.0,  # 4% of 10000
                "annualized_tracking_error": 2.0,
                "bars_with_divergence_above_threshold_pct": 5.0,
                "mean_divergence_bps": 40.0,
                "max_divergence_bps": 100.0,
            }
        ]
        initial_capital = 10000.0
        
        result = checker.check_tracking_error_rmse(tracking_error_stats, initial_capital)
        assert result.passed is True
        assert result.reason is None
    
    def test_check_tracking_error_rmse_fails(self):
        """Test that guardrail fails when RMSE exceeds threshold."""
        config = GuardrailConfig(max_tracking_error_rmse_pct=0.05)  # 5%
        checker = GuardrailChecker(config)
        
        tracking_error_stats = [
            {
                "rmse": 600.0,  # 6% of 10000
                "annualized_tracking_error": 3.0,
                "bars_with_divergence_above_threshold_pct": 8.0,
                "mean_divergence_bps": 60.0,
                "max_divergence_bps": 150.0,
            }
        ]
        initial_capital = 10000.0
        
        result = checker.check_tracking_error_rmse(tracking_error_stats, initial_capital)
        assert result.passed is False
        assert result.reason == CampaignRejectedReason.TRACKING_ERROR_TOO_HIGH
        assert result.details is not None
        assert result.details["rmse_pct"] == 0.06
        assert result.details["max_allowed_rmse_pct"] == 0.05
    
    def test_check_tracking_error_rmse_uses_latest_stats(self):
        """Test that guardrail uses the latest tracking_error_stats entry."""
        config = GuardrailConfig(max_tracking_error_rmse_pct=0.05)  # 5%
        checker = GuardrailChecker(config)
        
        tracking_error_stats = [
            {
                "rmse": 200.0,  # 2% - should pass
                "annualized_tracking_error": 1.0,
            },
            {
                "rmse": 600.0,  # 6% - should fail (this is the latest)
                "annualized_tracking_error": 3.0,
            }
        ]
        initial_capital = 10000.0
        
        result = checker.check_tracking_error_rmse(tracking_error_stats, initial_capital)
        assert result.passed is False
        assert result.details["rmse"] == 600.0  # Should use latest
    
    def test_check_tracking_error_rmse_handles_empty_stats(self):
        """Test that guardrail passes when tracking_error_stats is empty."""
        config = GuardrailConfig(max_tracking_error_rmse_pct=0.05)
        checker = GuardrailChecker(config)
        
        result = checker.check_tracking_error_rmse([], 10000.0)
        assert result.passed is True
    
    def test_check_tracking_error_rmse_handles_missing_rmse(self):
        """Test that guardrail passes when RMSE is missing from stats."""
        config = GuardrailConfig(max_tracking_error_rmse_pct=0.05)
        checker = GuardrailChecker(config)
        
        tracking_error_stats = [
            {
                "annualized_tracking_error": 2.0,
                # Missing rmse
            }
        ]
        
        result = checker.check_tracking_error_rmse(tracking_error_stats, 10000.0)
        assert result.passed is True
    
    def test_check_all_includes_rmse_check(self):
        """Test that check_all includes RMSE check when stats provided."""
        config = GuardrailConfig(max_tracking_error_rmse_pct=0.05)
        checker = GuardrailChecker(config)
        
        tracking_error_stats = [
            {
                "rmse": 600.0,  # 6% - should fail
                "annualized_tracking_error": 3.0,
            }
        ]
        
        result = checker.check_all(
            tracking_error_stats=tracking_error_stats,
            initial_capital=10000.0,
        )
        assert result.passed is False
        assert result.reason == CampaignRejectedReason.TRACKING_ERROR_TOO_HIGH

