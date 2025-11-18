"""Strategy implementations producing signals and trade metadata."""
from __future__ import annotations

from typing import Any, Literal

import pandas as pd

from app.quant.config_manager import get_signal_params

Signal = Literal["BUY", "SELL", "HOLD"]

# Load params using config manager for versioning support
PARAMS = get_signal_params()


def momentum_strategy(df: pd.DataFrame, ind: dict[str, pd.Series]) -> dict[str, Any]:
    if df.empty:
        return {"signal": "HOLD", "confidence": 0.0, "reason": "no_data"}
    ema9 = ind.get("ema_9", pd.Series())
    ema21 = ind.get("ema_21", pd.Series())
    ema50 = ind.get("ema_50", pd.Series())
    sma200 = ind.get("sma_200", pd.Series())
    macd = ind.get("macd", pd.Series())
    macd_sig = ind.get("macd_signal", pd.Series())
    if any(s.empty for s in [ema9, ema21, ema50, sma200, macd, macd_sig]):
        return {"signal": "HOLD", "confidence": 0.0, "reason": "missing_indicators"}
    price = df["close"].iloc[-1]
    buy = price > ema9.iloc[-1] > ema21.iloc[-1] > ema50.iloc[-1] > sma200.iloc[-1] and macd.iloc[-1] > macd_sig.iloc[-1]
    sell = price < ema9.iloc[-1] < ema21.iloc[-1] < ema50.iloc[-1] < sma200.iloc[-1] and macd.iloc[-1] < macd_sig.iloc[-1]
    momentum_params = PARAMS.get("momentum", {})
    confidence_buy = float(momentum_params.get("confidence_buy", 65.0))
    confidence_sell = float(momentum_params.get("confidence_sell", 65.0))
    confidence_hold = float(momentum_params.get("confidence_hold", 30.0))
    if buy:
        return {"signal": "BUY", "confidence": confidence_buy, "reason": "trend_alignment"}
    if sell:
        return {"signal": "SELL", "confidence": confidence_sell, "reason": "trend_alignment"}
    return {"signal": "HOLD", "confidence": confidence_hold, "reason": "no_alignment"}


def mean_reversion_strategy(df: pd.DataFrame, ind: dict[str, pd.Series]) -> dict[str, Any]:
    if df.empty:
        return {"signal": "HOLD", "confidence": 0.0, "reason": "no_data"}
    rsi = ind.get("rsi", pd.Series())
    bb_u = ind.get("bb_upper", pd.Series())
    bb_l = ind.get("bb_lower", pd.Series())
    if any(s.empty for s in [rsi, bb_u, bb_l]):
        return {"signal": "HOLD", "confidence": 0.0, "reason": "missing_indicators"}
    price = df["close"].iloc[-1]
    mean_params = PARAMS.get("mean_reversion", {})
    rsi_buy = float(mean_params.get("rsi_buy", 30))
    rsi_sell = float(mean_params.get("rsi_sell", 70))
    confidence_buy = float(mean_params.get("confidence_buy", 55.0))
    confidence_sell = float(mean_params.get("confidence_sell", 55.0))
    confidence_hold = float(mean_params.get("confidence_hold", 25.0))
    if price <= bb_l.iloc[-1] and rsi.iloc[-1] < rsi_buy:
        return {"signal": "BUY", "confidence": confidence_buy, "reason": "oversold_bounce"}
    if price >= bb_u.iloc[-1] and rsi.iloc[-1] > rsi_sell:
        return {"signal": "SELL", "confidence": confidence_sell, "reason": "overbought_pullback"}
    return {"signal": "HOLD", "confidence": confidence_hold, "reason": "neutral"}


def breakout_strategy(df: pd.DataFrame, ind: dict[str, pd.Series]) -> dict[str, Any]:
    breakout_params = PARAMS.get("breakout", {})
    lookback = int(breakout_params.get("lookback", 20))
    volume_multiple = float(breakout_params.get("volume_multiple", 1.5))
    confidence_buy = float(breakout_params.get("confidence_buy", 60.0))
    confidence_sell = float(breakout_params.get("confidence_sell", 60.0))
    confidence_hold = float(breakout_params.get("confidence_hold", 20.0))
    if df.empty or len(df) < lookback:
        return {"signal": "HOLD", "confidence": 0.0, "reason": "no_data"}
    vol = df["volume"].tail(lookback)
    price = df["close"].iloc[-1]
    recent_high = df["high"].tail(lookback).max()
    recent_low = df["low"].tail(lookback).min()
    avg_vol = vol.mean()
    cur_vol = df["volume"].iloc[-1]
    if price > recent_high and cur_vol > volume_multiple * avg_vol:
        return {"signal": "BUY", "confidence": confidence_buy, "reason": "breakout_up"}
    if price < recent_low and cur_vol > volume_multiple * avg_vol:
        return {"signal": "SELL", "confidence": confidence_sell, "reason": "breakout_down"}
    return {"signal": "HOLD", "confidence": confidence_hold, "reason": "no_breakout"}


def volatility_strategy(df: pd.DataFrame, ind: dict[str, pd.Series]) -> dict[str, Any]:
    if df.empty:
        return {"signal": "HOLD", "confidence": 0.0, "reason": "no_data"}
    rv = ind.get("realized_vol", pd.Series())
    a = ind.get("atr", pd.Series())
    if any(s.empty for s in [rv, a]):
        return {"signal": "HOLD", "confidence": 0.0, "reason": "missing_indicators"}
    vol_params = PARAMS.get("volatility", {})
    low_threshold = float(vol_params.get("low_threshold", 0.2))
    high_threshold = float(vol_params.get("high_threshold", 0.5))
    confidence_low = float(vol_params.get("confidence_low", 35.0))
    confidence_high = float(vol_params.get("confidence_high", 50.0))
    confidence_mid = float(vol_params.get("confidence_mid", 30.0))
    vol = float(rv.iloc[-1])
    if vol < low_threshold:
        return {"signal": "HOLD", "confidence": confidence_low, "reason": "low_vol_range"}
    if vol > high_threshold:
        # prefer breakouts in high vol
        return {"signal": "BUY", "confidence": confidence_high, "reason": "high_vol_trend"}
    return {"signal": "HOLD", "confidence": confidence_mid, "reason": "mid_vol"}


