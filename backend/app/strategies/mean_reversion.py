"""Mean-Reversion strategy."""
import pandas as pd
from typing import Dict, Any
from app.strategies.base import BaseStrategy, SignalType


class MeanReversionStrategy(BaseStrategy):
    """Strategy based on mean reversion principles."""

    def __init__(self):
        super().__init__("Mean-Reversion")

    def generate_signal(self, df: pd.DataFrame, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """Generate signal based on mean reversion."""
        if df.empty or len(df) < 100:
            return {"signal": "HOLD", "confidence": 0.0, "reason": "Insufficient data"}

        latest = df.iloc[-1]
        bb_upper = indicators.get("bb_upper", pd.Series())
        bb_lower = indicators.get("bb_lower", pd.Series())
        bb_middle = indicators.get("bb_middle", pd.Series())
        rsi = indicators.get("rsi", pd.Series())
        stoch_rsi = indicators.get("stoch_rsi", pd.Series())

        if any(s.empty for s in [bb_upper, bb_lower, bb_middle, rsi, stoch_rsi]):
            return {"signal": "HOLD", "confidence": 0.0, "reason": "Missing indicators"}

        current_price = latest["close"]
        bb_upper_val = bb_upper.iloc[-1]
        bb_lower_val = bb_lower.iloc[-1]
        bb_middle_val = bb_middle.iloc[-1]
        rsi_val = rsi.iloc[-1]
        stoch_rsi_val = stoch_rsi.iloc[-1]

        buy_signals = 0
        sell_signals = 0
        confidence = 0.0

        if current_price <= bb_lower_val and rsi_val < 30:
            buy_signals += 2
        elif current_price >= bb_upper_val and rsi_val > 70:
            sell_signals += 2

        if stoch_rsi_val < 20:
            buy_signals += 1
        elif stoch_rsi_val > 80:
            sell_signals += 1

        distance_from_mean = abs(current_price - bb_middle_val) / bb_middle_val
        if distance_from_mean > 0.02:
            if current_price < bb_middle_val:
                buy_signals += 1
            else:
                sell_signals += 1

        if buy_signals >= 2:
            signal: SignalType = "BUY"
            confidence = min(40.0 + (buy_signals * 15), 85.0)
        elif sell_signals >= 2:
            signal = "SELL"
            confidence = min(40.0 + (sell_signals * 15), 85.0)
        else:
            signal = "HOLD"
            confidence = 25.0

        return {"signal": signal, "confidence": confidence, "reason": f"Mean reversion signals: Buy={buy_signals}, Sell={sell_signals}"}

