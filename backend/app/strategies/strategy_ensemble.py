"""Strategy ensemble for signal consolidation."""
from typing import List, Dict, Any, Literal
import pandas as pd
from app.strategies.base import BaseStrategy, SignalType
from app.strategies.momentum_trend import MomentumTrendStrategy
from app.strategies.mean_reversion import MeanReversionStrategy
from app.strategies.breakout import BreakoutStrategy


class StrategyEnsemble:
    """Combine multiple strategies into consolidated signal."""

    def __init__(self):
        self.strategies: List[BaseStrategy] = [
            MomentumTrendStrategy(),
            MeanReversionStrategy(),
            BreakoutStrategy(),
        ]
        self.strategy_weights = {s.name: 1.0 / len(self.strategies) for s in self.strategies}

    def consolidate_signals(self, df: pd.DataFrame, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """Consolidate signals from all strategies."""
        signals = []
        total_confidence = 0.0

        for strategy in self.strategies:
            try:
                signal_data = strategy.generate_signal(df, indicators)
                signals.append(
                    {
                        "strategy": strategy.name,
                        "signal": signal_data["signal"],
                        "confidence": signal_data.get("confidence", 0.0),
                        "reason": signal_data.get("reason", ""),
                    }
                )
                weight = self.strategy_weights.get(strategy.name, 0.0)
                total_confidence += signal_data.get("confidence", 0.0) * weight
            except Exception as e:
                continue

        if not signals:
            return {"signal": "HOLD", "confidence": 0.0, "strategies": []}

        buy_votes = sum(1 for s in signals if s["signal"] == "BUY")
        sell_votes = sum(1 for s in signals if s["signal"] == "SELL")
        hold_votes = sum(1 for s in signals if s["signal"] == "HOLD")

        if buy_votes > sell_votes and buy_votes > hold_votes:
            consolidated_signal: SignalType = "BUY"
        elif sell_votes > buy_votes and sell_votes > hold_votes:
            consolidated_signal = "SELL"
        else:
            consolidated_signal = "HOLD"

        agreement = max(buy_votes, sell_votes, hold_votes) / len(signals) if signals else 0.0
        final_confidence = min(total_confidence * (1 + agreement), 95.0)

        return {
            "signal": consolidated_signal,
            "confidence": final_confidence,
            "agreement": agreement,
            "buy_votes": buy_votes,
            "sell_votes": sell_votes,
            "hold_votes": hold_votes,
            "strategies": signals,
        }

