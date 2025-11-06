"""Momentum-Trend strategy."""
import pandas as pd
from typing import Dict, Any
from app.strategies.base import BaseStrategy, SignalType


class MomentumTrendStrategy(BaseStrategy):
    """Strategy based on momentum and trend alignment."""

    def __init__(self):
        super().__init__("Momentum-Trend")

    def generate_signal(self, df: pd.DataFrame, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """Generate signal based on momentum and trend."""
        if df.empty or len(df) < 200:
            return {"signal": "HOLD", "confidence": 0.0, "reason": "Insufficient data"}

        latest = df.iloc[-1]
        ema_9 = indicators.get("ema_9", pd.Series())
        ema_21 = indicators.get("ema_21", pd.Series())
        ema_50 = indicators.get("ema_50", pd.Series())
        sma_200 = indicators.get("sma_200", pd.Series())
        rsi = indicators.get("rsi", pd.Series())
        macd = indicators.get("macd", pd.Series())
        macd_signal = indicators.get("macd_signal", pd.Series())

        if any(s.empty for s in [ema_9, ema_21, ema_50, sma_200, rsi, macd, macd_signal]):
            return {"signal": "HOLD", "confidence": 0.0, "reason": "Missing indicators"}

        current_price = latest["close"]
        ema_9_val = ema_9.iloc[-1]
        ema_21_val = ema_21.iloc[-1]
        ema_50_val = ema_50.iloc[-1]
        sma_200_val = sma_200.iloc[-1]
        rsi_val = rsi.iloc[-1]
        macd_val = macd.iloc[-1]
        macd_signal_val = macd_signal.iloc[-1]

        buy_signals = 0
        sell_signals = 0
        confidence = 0.0

        if current_price > ema_9_val > ema_21_val > ema_50_val > sma_200_val:
            buy_signals += 2
        elif current_price < ema_9_val < ema_21_val < ema_50_val < sma_200_val:
            sell_signals += 2

        if macd_val > macd_signal_val and macd_val > 0:
            buy_signals += 1
        elif macd_val < macd_signal_val and macd_val < 0:
            sell_signals += 1

        if 30 < rsi_val < 70:
            if buy_signals > sell_signals:
                buy_signals += 1
            elif sell_signals > buy_signals:
                sell_signals += 1

        if buy_signals > sell_signals and buy_signals >= 2:
            signal: SignalType = "BUY"
            confidence = min(50.0 + (buy_signals * 10), 90.0)
        elif sell_signals > buy_signals and sell_signals >= 2:
            signal = "SELL"
            confidence = min(50.0 + (sell_signals * 10), 90.0)
        else:
            signal = "HOLD"
            confidence = 30.0

        return {"signal": signal, "confidence": confidence, "reason": f"Buy signals: {buy_signals}, Sell signals: {sell_signals}"}

