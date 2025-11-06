"""Strategy implementations producing signals and trade metadata."""
from __future__ import annotations

from typing import Dict, Any, Literal
import pandas as pd

Signal = Literal["BUY", "SELL", "HOLD"]


def momentum_strategy(df: pd.DataFrame, ind: Dict[str, pd.Series]) -> Dict[str, Any]:
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
    if buy:
        return {"signal": "BUY", "confidence": 65.0, "reason": "trend_alignment"}
    if sell:
        return {"signal": "SELL", "confidence": 65.0, "reason": "trend_alignment"}
    return {"signal": "HOLD", "confidence": 30.0, "reason": "no_alignment"}


def mean_reversion_strategy(df: pd.DataFrame, ind: Dict[str, pd.Series]) -> Dict[str, Any]:
    if df.empty:
        return {"signal": "HOLD", "confidence": 0.0, "reason": "no_data"}
    rsi = ind.get("rsi", pd.Series())
    bb_u = ind.get("bb_upper", pd.Series())
    bb_l = ind.get("bb_lower", pd.Series())
    if any(s.empty for s in [rsi, bb_u, bb_l]):
        return {"signal": "HOLD", "confidence": 0.0, "reason": "missing_indicators"}
    price = df["close"].iloc[-1]
    if price <= bb_l.iloc[-1] and rsi.iloc[-1] < 30:
        return {"signal": "BUY", "confidence": 55.0, "reason": "oversold_bounce"}
    if price >= bb_u.iloc[-1] and rsi.iloc[-1] > 70:
        return {"signal": "SELL", "confidence": 55.0, "reason": "overbought_pullback"}
    return {"signal": "HOLD", "confidence": 25.0, "reason": "neutral"}


def breakout_strategy(df: pd.DataFrame, ind: Dict[str, pd.Series]) -> Dict[str, Any]:
    if df.empty or len(df) < 20:
        return {"signal": "HOLD", "confidence": 0.0, "reason": "no_data"}
    vol = df["volume"].tail(20)
    price = df["close"].iloc[-1]
    recent_high = df["high"].tail(20).max()
    recent_low = df["low"].tail(20).min()
    avg_vol = vol.mean()
    cur_vol = df["volume"].iloc[-1]
    if price > recent_high and cur_vol > 1.5 * avg_vol:
        return {"signal": "BUY", "confidence": 60.0, "reason": "breakout_up"}
    if price < recent_low and cur_vol > 1.5 * avg_vol:
        return {"signal": "SELL", "confidence": 60.0, "reason": "breakout_down"}
    return {"signal": "HOLD", "confidence": 20.0, "reason": "no_breakout"}


def volatility_strategy(df: pd.DataFrame, ind: Dict[str, pd.Series]) -> Dict[str, Any]:
    if df.empty:
        return {"signal": "HOLD", "confidence": 0.0, "reason": "no_data"}
    rv = ind.get("realized_vol", pd.Series())
    a = ind.get("atr", pd.Series())
    if any(s.empty for s in [rv, a]):
        return {"signal": "HOLD", "confidence": 0.0, "reason": "missing_indicators"}
    vol = float(rv.iloc[-1])
    if vol < 0.2:
        return {"signal": "HOLD", "confidence": 35.0, "reason": "low_vol_range"}
    if vol > 0.5:
        # prefer breakouts in high vol
        return {"signal": "BUY", "confidence": 50.0, "reason": "high_vol_trend"}
    return {"signal": "HOLD", "confidence": 30.0, "reason": "mid_vol"}


