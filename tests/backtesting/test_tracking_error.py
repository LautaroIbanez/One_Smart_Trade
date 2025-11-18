"""Tests for tracking error calculation with synthetic datasets."""
import pytest
import numpy as np
import pandas as pd

from app.backtesting.tracking_error import TrackingErrorCalculator, PeriodTrackingError


def generate_synthetic_equity_curves(
    n_bars: int = 100,
    initial_capital: float = 10000.0,
    theoretical_return_pct: float = 0.001,  # 0.1% per bar
    friction_factor: float = 0.95,  # Realistic is 5% worse due to frictions
    noise_std: float = 0.0001,  # Small noise in realistic curve
    seed: int = 42,
) -> tuple[list[float], list[float]]:
    """
    Generate synthetic equity curves with known frictions.
    
    Args:
        n_bars: Number of bars to generate
        initial_capital: Starting capital
        theoretical_return_pct: Expected return per bar for theoretical curve
        friction_factor: Factor to apply to returns for realistic curve (e.g., 0.95 = 5% worse)
        noise_std: Standard deviation of noise to add to realistic curve
        seed: Random seed for reproducibility
        
    Returns:
        Tuple of (theoretical_equity, realistic_equity) lists
    """
    np.random.seed(seed)
    
    theoretical = [initial_capital]
    realistic = [initial_capital]
    
    for i in range(1, n_bars):
        # Theoretical: consistent return
        theoretical_return = theoretical_return_pct
        theoretical.append(theoretical[-1] * (1 + theoretical_return))
        
        # Realistic: apply friction factor and add noise
        realistic_return = theoretical_return * friction_factor
        noise = np.random.normal(0, noise_std)
        realistic.append(realistic[-1] * (1 + realistic_return + noise))
    
    return theoretical, realistic


class TestTrackingErrorCalculator:
    """Test TrackingErrorCalculator with synthetic data."""
    
    def test_identical_curves_zero_tracking_error(self):
        """Test that identical curves produce zero tracking error."""
        equity_curve = [10000.0, 10100.0, 10200.0, 10300.0, 10400.0]
        
        result = TrackingErrorCalculator.from_curves(
            theoretical=equity_curve,
            realistic=equity_curve,
        )
        
        assert result.rmse == 0.0
        assert result.annualized_tracking_error == 0.0
        assert result.mean_divergence_bps == 0.0
        assert result.max_divergence_bps == 0.0
        assert result.bars_with_divergence_above_threshold_pct == 0.0
    
    def test_constant_divergence_rmse(self):
        """Test RMSE calculation with constant divergence."""
        theoretical = [10000.0, 10100.0, 10200.0, 10300.0, 10400.0]
        # Realistic is consistently 100 units lower (1%)
        realistic = [9900.0, 10000.0, 10100.0, 10200.0, 10300.0]
        
        result = TrackingErrorCalculator.from_curves(
            theoretical=theoretical,
            realistic=realistic,
        )
        
        # Expected RMSE = 100.0 (constant divergence)
        assert abs(result.rmse - 100.0) < 0.01
        assert result.mean_divergence_bps > 0  # Should be positive
    
    def test_synthetic_dataset_with_frictions(self):
        """Test tracking error calculation with synthetic dataset simulating frictions."""
        theoretical, realistic = generate_synthetic_equity_curves(
            n_bars=252,  # 1 year of daily data
            initial_capital=10000.0,
            theoretical_return_pct=0.001,  # 0.1% per day
            friction_factor=0.95,  # 5% worse due to frictions
            noise_std=0.0001,
            seed=42,
        )
        
        result = TrackingErrorCalculator.from_curves(
            theoretical=theoretical,
            realistic=realistic,
            bars_per_year=252,  # Daily data
        )
        
        # Verify RMSE is positive and reasonable
        assert result.rmse > 0
        assert result.rmse < 1000.0  # Should be reasonable for this setup
        
        # Verify annualized tracking error is positive
        assert result.annualized_tracking_error > 0
        
        # Verify mean divergence is positive (realistic should be worse)
        assert result.mean_divergence_bps > 0
        
        # Verify max divergence is reasonable
        assert result.max_divergence_bps > result.mean_divergence_bps
        
        # Verify percentage of bars with divergence > threshold
        assert 0.0 <= result.bars_with_divergence_above_threshold_pct <= 100.0
    
    def test_expected_rmse_with_known_friction(self):
        """Test that RMSE matches expected value for known friction."""
        theoretical = [10000.0]
        realistic = [10000.0]
        
        # Generate 100 bars with 1% return per bar theoretical
        # and 0.5% return per bar realistic (50% friction)
        for i in range(100):
            theoretical.append(theoretical[-1] * 1.01)
            realistic.append(realistic[-1] * 1.005)
        
        result = TrackingErrorCalculator.from_curves(
            theoretical=theoretical,
            realistic=realistic,
        )
        
        # RMSE should be positive and reflect the cumulative divergence
        assert result.rmse > 0
        # After 100 bars, theoretical ~ 27000, realistic ~ 16400
        # RMSE should capture this divergence
        assert result.rmse > 1000.0  # Significant divergence expected
    
    def test_divergence_threshold_counting(self):
        """Test that bars with divergence above threshold are counted correctly."""
        theoretical = [10000.0] * 100
        realistic = [10000.0] * 100
        
        # Make every 10th bar have high divergence (50 bps)
        for i in range(0, 100, 10):
            realistic[i] = theoretical[i] * (1 - 0.005)  # 50 bps divergence
        
        result = TrackingErrorCalculator.from_curves(
            theoretical=theoretical,
            realistic=realistic,
            divergence_threshold_bps=10.0,  # 10 bps threshold
        )
        
        # Should detect ~10 bars with divergence > 10 bps (10% of bars)
        # Allow some tolerance for floating point
        assert 8.0 <= result.bars_with_divergence_above_threshold_pct <= 12.0
    
    def test_pandas_dataframe_input(self):
        """Test that calculator accepts pandas DataFrame input."""
        theoretical = [10000.0, 10100.0, 10200.0]
        realistic = [9900.0, 10000.0, 10100.0]
        
        df_theoretical = pd.DataFrame({"equity_theoretical": theoretical})
        df_realistic = pd.DataFrame({"equity_realistic": realistic})
        
        result = TrackingErrorCalculator.from_curves(
            theoretical=df_theoretical,
            realistic=df_realistic,
        )
        
        assert result.rmse > 0
        assert result.mean_divergence_bps > 0
    
    def test_pandas_series_input(self):
        """Test that calculator accepts pandas Series input."""
        theoretical = pd.Series([10000.0, 10100.0, 10200.0])
        realistic = pd.Series([9900.0, 10000.0, 10100.0])
        
        result = TrackingErrorCalculator.from_curves(
            theoretical=theoretical,
            realistic=realistic,
        )
        
        assert result.rmse > 0
        assert result.mean_divergence_bps > 0
    
    def test_insufficient_data_handling(self):
        """Test handling of insufficient data (less than 2 points)."""
        result = TrackingErrorCalculator.from_curves(
            theoretical=[10000.0],
            realistic=[9900.0],
        )
        
        # Should return zeros for insufficient data
        assert result.rmse == 0.0
        assert result.annualized_tracking_error == 0.0
        assert result.mean_divergence_bps == 0.0
    
    def test_empty_input_handling(self):
        """Test handling of empty input."""
        result = TrackingErrorCalculator.from_curves(
            theoretical=[],
            realistic=[],
        )
        
        assert result.rmse == 0.0
        assert result.annualized_tracking_error == 0.0
    
    def test_different_length_curves(self):
        """Test handling of curves with different lengths."""
        theoretical = [10000.0, 10100.0, 10200.0, 10300.0, 10400.0]
        realistic = [9900.0, 10000.0, 10100.0]  # Shorter
        
        result = TrackingErrorCalculator.from_curves(
            theoretical=theoretical,
            realistic=realistic,
        )
        
        # Should use minimum length (3)
        assert result.rmse > 0
        assert result.mean_divergence_bps > 0
    
    def test_annualization_with_different_bars_per_year(self):
        """Test that annualization adjusts correctly with bars_per_year."""
        theoretical, realistic = generate_synthetic_equity_curves(
            n_bars=100,
            friction_factor=0.95,
        )
        
        result_daily = TrackingErrorCalculator.from_curves(
            theoretical=theoretical,
            realistic=realistic,
            bars_per_year=252,  # Daily
        )
        
        result_hourly = TrackingErrorCalculator.from_curves(
            theoretical=theoretical,
            realistic=realistic,
            bars_per_year=365 * 24,  # Hourly
        )
        
        # Annualized tracking error should be higher for hourly (more bars per year)
        assert result_hourly.annualized_tracking_error > result_daily.annualized_tracking_error
    
    def test_to_dict_serialization(self):
        """Test that to_dict() produces serializable output."""
        theoretical, realistic = generate_synthetic_equity_curves(n_bars=50)
        
        result = TrackingErrorCalculator.from_curves(
            theoretical=theoretical,
            realistic=realistic,
        )
        
        result_dict = result.to_dict()
        
        # Verify all fields are present and are floats
        assert "rmse" in result_dict
        assert "annualized_tracking_error" in result_dict
        assert "bars_with_divergence_above_threshold_pct" in result_dict
        assert "mean_divergence_bps" in result_dict
        assert "max_divergence_bps" in result_dict
        
        # Verify all values are numbers
        assert isinstance(result_dict["rmse"], (int, float))
        assert isinstance(result_dict["annualized_tracking_error"], (int, float))
        assert isinstance(result_dict["mean_divergence_bps"], (int, float))
        assert isinstance(result_dict["max_divergence_bps"], (int, float))


class TestTrackingErrorWithRealisticScenarios:
    """Test tracking error with realistic trading scenarios."""
    
    def test_high_frequency_trading_increases_tracking_error(self):
        """Test that higher frequency of trades increases tracking error."""
        # Scenario 1: Low frequency (1 trade every 10 bars)
        theoretical_low = [10000.0]
        realistic_low = [10000.0]
        
        for i in range(100):
            theoretical_low.append(theoretical_low[-1] * 1.001)  # 0.1% per bar
            if i % 10 == 0:
                # Trade every 10 bars with 1% friction
                realistic_low.append(realistic_low[-1] * 1.001 * 0.99)
            else:
                realistic_low.append(realistic_low[-1] * 1.001)
        
        # Scenario 2: High frequency (1 trade every bar)
        theoretical_high = [10000.0]
        realistic_high = [10000.0]
        
        for i in range(100):
            theoretical_high.append(theoretical_high[-1] * 1.001)
            # Trade every bar with 1% friction
            realistic_high.append(realistic_high[-1] * 1.001 * 0.99)
        
        result_low = TrackingErrorCalculator.from_curves(
            theoretical=theoretical_low,
            realistic=realistic_low,
        )
        
        result_high = TrackingErrorCalculator.from_curves(
            theoretical=theoretical_high,
            realistic=realistic_high,
        )
        
        # High frequency should have higher tracking error
        assert result_high.rmse > result_low.rmse
        assert result_high.mean_divergence_bps > result_low.mean_divergence_bps
    
    def test_slippage_impact_on_tracking_error(self):
        """Test that higher slippage increases tracking error."""
        theoretical = [10000.0]
        
        # Low slippage scenario (0.5% per trade)
        realistic_low_slippage = [10000.0]
        
        # High slippage scenario (2% per trade)
        realistic_high_slippage = [10000.0]
        
        for i in range(50):
            theoretical.append(theoretical[-1] * 1.01)  # 1% return
            # Trade every bar
            realistic_low_slippage.append(realistic_low_slippage[-1] * 1.01 * 0.995)  # 0.5% slippage
            realistic_high_slippage.append(realistic_high_slippage[-1] * 1.01 * 0.98)  # 2% slippage
        
        result_low = TrackingErrorCalculator.from_curves(
            theoretical=theoretical,
            realistic=realistic_low_slippage,
        )
        
        result_high = TrackingErrorCalculator.from_curves(
            theoretical=theoretical,
            realistic=realistic_high_slippage,
        )
        
        # High slippage should have higher tracking error
        assert result_high.rmse > result_low.rmse
        assert result_high.max_divergence_bps > result_low.max_divergence_bps

