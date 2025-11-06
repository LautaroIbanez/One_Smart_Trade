"""Tests for strategies and signal engine consolidation."""
import pandas as pd
import numpy as np
from app.quant import indicators as ind
from app.quant.strategies import momentum_strategy, mean_reversion_strategy, breakout_strategy, volatility_strategy
from app.quant.signal_engine import generate_signal


def _mk_df(n=300):
    idx = pd.date_range("2022-01-01", periods=n, freq="D")
    price = np.linspace(30000, 35000, n) + np.random.normal(0, 200, n).cumsum()
    high = price + np.random.uniform(20, 100, n)
    low = price - np.random.uniform(20, 100, n)
    close = price
    open_ = price + np.random.uniform(-40, 40, n)
    volume = np.random.uniform(100, 400, n)
    return pd.DataFrame({"open_time": idx, "open": open_, "high": high, "low": low, "close": close, "volume": volume})


def test_strategies_produce_signals():
    df = _mk_df()
    indicators = ind.calculate_all(df)
    for s in (momentum_strategy, mean_reversion_strategy, breakout_strategy, volatility_strategy):
        out = s(df, indicators)
        assert out["signal"] in ("BUY", "SELL", "HOLD")
        assert "confidence" in out


def test_signal_engine_consolidation():
    df_d = _mk_df(400)
    # Synthesize 1h by upsampling and noise
    df_h = df_d.copy().iloc[-200:].reset_index(drop=True)
    df_h.index = pd.date_range(df_d["open_time"].iloc[-200], periods=len(df_h), freq="H")
    df_h["open_time"] = df_h.index
    df_h["close"] = df_h["close"] + np.random.normal(0, 50, len(df_h)).cumsum()
    sig = generate_signal(df_h, df_d)
    assert sig["signal"] in ("BUY", "SELL", "HOLD")
    assert "entry_range" in sig and "stop_loss_take_profit" in sig
    assert 0 <= sig["confidence"] <= 100

