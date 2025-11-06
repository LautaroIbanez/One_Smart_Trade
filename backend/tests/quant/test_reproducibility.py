"""Tests for reproducibility with fixed seeds."""
import pytest
import numpy as np
import pandas as pd
from app.quant import indicators as ind
from app.quant.signal_engine import generate_signal


def _mk_df_seeded(n=300, seed=42):
    """Generate deterministic dataframe with seed."""
    np.random.seed(seed)
    idx = pd.date_range("2022-01-01", periods=n, freq="D")
    price = np.linspace(30000, 35000, n) + np.random.normal(0, 200, n).cumsum()
    high = price + np.random.uniform(20, 100, n)
    low = price - np.random.uniform(20, 100, n)
    close = price
    open_ = price + np.random.uniform(-40, 40, n)
    volume = np.random.uniform(100, 400, n)
    return pd.DataFrame({"open_time": idx, "open": open_, "high": high, "low": low, "close": close, "volume": volume})


def test_indicators_reproducible():
    """Test that indicators produce same results with same seed."""
    df1 = _mk_df_seeded(seed=42)
    df2 = _mk_df_seeded(seed=42)
    
    ind1 = ind.calculate_all(df1)
    ind2 = ind.calculate_all(df2)
    
    for key in ind1:
        np.testing.assert_array_almost_equal(ind1[key].values, ind2[key].values, decimal=5)


def test_signal_engine_reproducible():
    """Test that signal engine produces same results with same seed."""
    df_d1 = _mk_df_seeded(400, seed=42)
    df_h1 = _mk_df_seeded(600, seed=42)
    df_d2 = _mk_df_seeded(400, seed=42)
    df_h2 = _mk_df_seeded(600, seed=42)
    
    # Set seed for Monte Carlo in signal engine
    np.random.seed(42)
    sig1 = generate_signal(df_h1, df_d1)
    
    np.random.seed(42)
    sig2 = generate_signal(df_h2, df_d2)
    
    assert sig1["signal"] == sig2["signal"]
    assert abs(sig1["confidence"] - sig2["confidence"]) < 0.1  # Small tolerance for MC
    assert abs(sig1["entry_range"]["optimal"] - sig2["entry_range"]["optimal"]) < 0.01

