"""Cross-timeframe factors and market structure features."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def slope(series: pd.Series, window: int = 10) -> pd.Series:
    """Compute slope via linear regression over rolling window."""
    if series.empty:
        return series
    x = np.arange(window)
    def _sl(y):
        if len(y) < window:
            return np.nan
        b1 = np.polyfit(x, y, 1)[0]
        return b1
    return series.rolling(window).apply(lambda y: _sl(np.array(y)), raw=False)


def regime_volatility(realized_vol: pd.Series, high: float = 0.5, low: float = 0.2) -> pd.Series:
    """
    Map realized vol to regimes: 2=high,1=mid,0=low.

    Thresholds:
    - high: 0.5 (50% annualized volatility) - above this is high vol regime
    - low: 0.2 (20% annualized volatility) - below this is low vol regime
    Normalization: Annualized volatility (252 trading days).
    """
    return pd.Series(np.where(realized_vol > high, 2, np.where(realized_vol < low, 0, 1)), index=realized_vol.index)


def divergence(price: pd.Series, osc: pd.Series, window: int = 14) -> pd.Series:
    """
    Simple divergence detector: price higher high but osc lower high (bear) / opposite (bull).

    Returns: 1 for bullish divergence, -1 for bearish divergence, 0 for none.
    Window: 14 periods default (adjustable based on timeframe).
    """
    hh_price = price.rolling(window).apply(np.nanmax)
    hh_osc = osc.rolling(window).apply(np.nanmax)
    ll_price = price.rolling(window).apply(np.nanmin)
    ll_osc = osc.rolling(window).apply(np.nanmin)
    bear = ((price >= hh_price) & (osc <= hh_osc.shift(1))).astype(int)
    bull = ((price <= ll_price) & (osc >= ll_osc.shift(1))).astype(int)
    return bull - bear


def cross_timeframe(df_1h: pd.DataFrame, df_1d: pd.DataFrame, ind_1h: dict[str, pd.Series], ind_1d: dict[str, pd.Series]) -> dict[str, Any]:
    """Compute cross-timeframe factors (momentum alignment, volatility regime, divergences, slopes)."""
    # Align on latest available timestamps
    p1h = df_1h["close"].iloc[-1]
    p1d = df_1d["close"].iloc[-1]

    mom_1h = (df_1h["close"].iloc[-1] - df_1h["close"].iloc[-10]) / df_1h["close"].iloc[-10]
    mom_1d = (df_1d["close"].iloc[-1] - df_1d["close"].iloc[-10]) / df_1d["close"].iloc[-10]

    align_momentum = float(np.sign(mom_1h) == np.sign(mom_1d))

    slope_1h = float(slope(ind_1h["ema_21"], 20).iloc[-1]) if "ema_21" in ind_1h else 0.0
    slope_1d = float(slope(ind_1d["ema_21"], 20).iloc[-1]) if "ema_21" in ind_1d else 0.0

    rsi_div_1h = float(divergence(df_1h["close"], ind_1h["rsi"], 14).iloc[-1]) if "rsi" in ind_1h else 0.0
    rsi_div_1d = float(divergence(df_1d["close"], ind_1d["rsi"], 14).iloc[-1]) if "rsi" in ind_1d else 0.0

    reg_1h = int(regime_volatility(ind_1h["realized_vol"]).iloc[-1]) if "realized_vol" in ind_1h else 1
    reg_1d = int(regime_volatility(ind_1d["realized_vol"]).iloc[-1]) if "realized_vol" in ind_1d else 1

    return {
        "momentum_alignment": align_momentum,
        "slope_1h": slope_1h,
        "slope_1d": slope_1d,
        "divergence_1h": rsi_div_1h,
        "divergence_1d": rsi_div_1d,
        "vol_regime_1h": reg_1h,
        "vol_regime_1d": reg_1d,
        "mom_1h": float(mom_1h),
        "mom_1d": float(mom_1d),
    }


