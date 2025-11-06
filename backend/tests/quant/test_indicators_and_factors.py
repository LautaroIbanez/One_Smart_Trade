"""Tests for indicators and cross-timeframe factors."""
import pandas as pd
import numpy as np
from app.quant import indicators as ind
from app.quant.factors import cross_timeframe


def _mk_df(n=300):
    idx = pd.date_range("2022-01-01", periods=n, freq="H")
    price = np.linspace(30000, 35000, n) + np.random.normal(0, 100, n).cumsum()
    high = price + np.random.uniform(10, 50, n)
    low = price - np.random.uniform(10, 50, n)
    close = price
    open_ = price + np.random.uniform(-20, 20, n)
    volume = np.random.uniform(50, 200, n)
    return pd.DataFrame({"open_time": idx, "open": open_, "high": high, "low": low, "close": close, "volume": volume})


def test_indicators_calculate_all():
    df = _mk_df()
    out = ind.calculate_all(df)
    keys = ["ema_9", "ema_21", "ema_50", "sma_100", "sma_200", "macd", "macd_signal", "macd_histogram", "rsi", "stoch_rsi", "bb_upper", "bb_middle", "bb_lower", "kc_upper", "kc_middle", "kc_lower", "atr", "vwap", "realized_vol"]
    for k in keys:
        assert k in out
        assert not out[k].empty


def test_cross_timeframe_factors():
    df_h = _mk_df(600)
    df_d = _mk_df(400)
    ind_h = ind.calculate_all(df_h)
    ind_d = ind.calculate_all(df_d)
    f = cross_timeframe(df_h, df_d, ind_h, ind_d)
    assert "momentum_alignment" in f
    assert "slope_1h" in f
    assert "vol_regime_1d" in f or "vol_regime_1h" in f


