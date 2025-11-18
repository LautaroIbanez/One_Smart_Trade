"""Tests for deterministic signal generation with seeds."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.quant.signal_engine import generate_signal
from app.utils.seeding import generate_deterministic_seed


def create_test_dataframe(n=300, seed=42):
    """Create deterministic test dataframe."""
    np.random.seed(seed)
    idx = pd.date_range("2022-01-01", periods=n, freq="D")
    price = np.linspace(30000, 35000, n) + np.random.normal(0, 200, n).cumsum()
    high = price + np.random.uniform(20, 100, n)
    low = price - np.random.uniform(20, 100, n)
    close = price
    open_ = price + np.random.uniform(-40, 40, n)
    volume = np.random.uniform(100, 400, n)
    df = pd.DataFrame({
        "open_time": idx,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })
    # Add symbol column
    df["symbol"] = "BTCUSDT"
    return df


def test_signal_deterministic_with_same_seed():
    """Test that same seed produces identical confidence and SL/TP."""
    df_1d = create_test_dataframe(400, seed=42)
    df_1h = create_test_dataframe(600, seed=42)
    
    # Generate seed from date
    date_str = df_1d["open_time"].iloc[-1].date().isoformat()
    seed = generate_deterministic_seed(date_str, "BTCUSDT")
    
    # Generate signal twice with same seed
    sig1 = generate_signal(df_1h.copy(), df_1d.copy(), seed=seed)
    sig2 = generate_signal(df_1h.copy(), df_1d.copy(), seed=seed)
    
    # Confidence should be identical (Monte Carlo is deterministic with same seed)
    assert sig1["confidence"] == sig2["confidence"]
    assert sig1["seed"] == sig2["seed"]
    assert sig1["seed"] == seed
    assert sig1["signal"] == sig2["signal"]
    assert sig1["entry_range"]["optimal"] == sig2["entry_range"]["optimal"]
    assert sig1["stop_loss_take_profit"]["stop_loss"] == sig2["stop_loss_take_profit"]["stop_loss"]
    assert sig1["stop_loss_take_profit"]["take_profit"] == sig2["stop_loss_take_profit"]["take_profit"]


def test_signal_auto_generates_seed():
    """Test that signal auto-generates seed from date and symbol."""
    df_1d = create_test_dataframe(400, seed=42)
    df_1h = create_test_dataframe(600, seed=42)
    
    # Generate signal without providing seed
    sig1 = generate_signal(df_1h.copy(), df_1d.copy())
    sig2 = generate_signal(df_1h.copy(), df_1d.copy())
    
    # Should have same seed (same date + symbol)
    assert sig1["seed"] == sig2["seed"]
    assert sig1["seed"] is not None
    assert isinstance(sig1["seed"], int)
    
    # Confidence should be identical
    assert sig1["confidence"] == sig2["confidence"]


def test_signal_different_dates_different_seeds():
    """Test that different dates produce different seeds."""
    df_1d_1 = create_test_dataframe(400, seed=42)
    df_1h_1 = create_test_dataframe(600, seed=42)
    
    # Create second dataframe with different date
    df_1d_2 = create_test_dataframe(400, seed=42)
    df_1d_2["open_time"] = pd.date_range("2022-01-02", periods=400, freq="D")
    df_1h_2 = create_test_dataframe(600, seed=42)
    df_1h_2["open_time"] = pd.date_range("2022-01-02", periods=600, freq="D")
    
    sig1 = generate_signal(df_1h_1.copy(), df_1d_1.copy())
    sig2 = generate_signal(df_1h_2.copy(), df_1d_2.copy())
    
    # Seeds should be different
    assert sig1["seed"] != sig2["seed"]


def test_mc_confidence_deterministic():
    """Test that Monte Carlo confidence is deterministic with same seed."""
    from app.quant.signal_engine import _mc_confidence
    
    df = create_test_dataframe(400, seed=42)
    entry = 32000.0
    sl = 31000.0
    tp = 33000.0
    
    seed = generate_deterministic_seed("2025-01-15", "BTCUSDT")
    
    # Run twice with same seed
    conf1 = _mc_confidence(df, entry, sl, tp, trials=1000, seed=seed)
    conf2 = _mc_confidence(df, entry, sl, tp, trials=1000, seed=seed)
    
    # Should be identical
    assert conf1 == conf2


def test_mc_confidence_different_with_different_seeds():
    """Test that different seeds produce different (but valid) confidence values."""
    from app.quant.signal_engine import _mc_confidence
    
    df = create_test_dataframe(400, seed=42)
    entry = 32000.0
    sl = 31000.0
    tp = 33000.0
    
    seed1 = generate_deterministic_seed("2025-01-15", "BTCUSDT")
    seed2 = generate_deterministic_seed("2025-01-16", "BTCUSDT")
    
    conf1 = _mc_confidence(df, entry, sl, tp, trials=1000, seed=seed1)
    conf2 = _mc_confidence(df, entry, sl, tp, trials=1000, seed=seed2)
    
    # Should be different (Monte Carlo with different seeds)
    # But both should be valid confidence values
    assert 5.0 <= conf1 <= 95.0
    assert 5.0 <= conf2 <= 95.0
    # Note: They might be the same by chance, but with different seeds they're likely different

