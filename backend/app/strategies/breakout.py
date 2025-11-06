"""Breakout strategy."""
import pandas as pd
from typing import Dict, Any
from app.strategies.base import BaseStrategy, SignalType


class BreakoutStrategy(BaseStrategy):
    """Strategy based on breakout detection."""

    def __init__(self):
        super().__init__("Breakout")

    def generate_signal(self, df: pd.DataFrame, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """Generate signal based on breakouts."""
        if df.empty or len(df) < 50:
            return {"signal": "HOLD", "confidence": 0.0, "reason": "Insufficient data"}

        latest = df.iloc[-1]
        volume = df["volume"]
        atr = indicators.get("atr", pd.Series())
        adx = indicators.get("adx", pd.Series())
        bb_upper = indicators.get("bb_upper", pd.Series())
        bb_lower = indicators.get("bb_lower", pd.Series())

        if any(s.empty for s in [atr, adx, bb_upper, bb_lower]):
            return {"signal": "HOLD", "confidence": 0.0, "reason": "Missing indicators"}

        current_price = latest["close"]
        current_volume = latest["volume"]
        avg_volume = volume.tail(20).mean()
        atr_val = atr.iloc[-1]
        adx_val = adx.iloc[-1]
        bb_upper_val = bb_upper.iloc[-1]
        bb_lower_val = bb_lower.iloc[-1]

        recent_high = df["high"].tail(20).max()
        recent_low = df["low"].tail(20).min()

        buy_signals = 0
        sell_signals = 0
        confidence = 0.0

        if current_price > recent_high and current_volume > avg_volume * 1.5:
            buy_signals += 2
        elif current_price < recent_low and current_volume > avg_volume * 1.5:
            sell_signals += 2

        if adx_val > 25:
            if current_price > bb_upper_val:
                buy_signals += 1
            elif current_price < bb_lower_val:
                sell_signals += 1

        if current_volume > avg_volume * 2:
            if buy_signals > 0:
                buy_signals += 1
            elif sell_signals > 0:
                sell_signals += 1

        if buy_signals >= 2:
            signal: SignalType = "BUY"
            confidence = min(45.0 + (buy_signals * 12), 88.0)
        elif sell_signals >= 2:
            signal = "SELL"
            confidence = min(45.0 + (sell_signals * 12), 88.0)
        else:
            signal = "HOLD"
            confidence = 20.0

        return {"signal": signal, "confidence": confidence, "reason": f"Breakout signals: Buy={buy_signals}, Sell={sell_signals}"}

