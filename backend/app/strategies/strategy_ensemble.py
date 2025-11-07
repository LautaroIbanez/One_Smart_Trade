"""Strategy ensemble for signal consolidation."""
from typing import Any

import pandas as pd

from app.strategies.base import BaseStrategy, SignalType
from app.strategies.breakout import BreakoutStrategy
from app.strategies.mean_reversion import MeanReversionStrategy
from app.strategies.momentum_trend import MomentumTrendStrategy


class StrategyEnsemble:
    """Combine multiple strategies into consolidated signal."""

    def __init__(self):
        self.strategies: list[BaseStrategy] = [
            MomentumTrendStrategy(),
            MeanReversionStrategy(),
            BreakoutStrategy(),
        ]
        self.strategy_weights = {s.name: 1.0 / len(self.strategies) for s in self.strategies}

    def consolidate_signals(self, df: pd.DataFrame, indicators: dict[str, Any]) -> dict[str, Any]:
        """Consolidate signals from all strategies."""
        signals: list[dict[str, Any]] = []
        weighted_confidence = 0.0
        valid_weight_total = 0.0

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
                reason = signal_data.get("reason", "").lower()
                confidence = float(signal_data.get("confidence", 0.0))
                is_valid = confidence > 0.0 and "missing" not in reason
                if is_valid:
                    weighted_confidence += confidence * weight
                    valid_weight_total += weight
            except Exception:
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
        base_confidence = (
            weighted_confidence / valid_weight_total if valid_weight_total > 0 else 0.0
        )
        integrity_factor = max(min(valid_weight_total, 1.0), 0.0)
        final_confidence = min(base_confidence * agreement * (0.6 + 0.4 * integrity_factor), 90.0)

        return {
            "signal": consolidated_signal,
            "confidence": final_confidence,
            "agreement": agreement,
            "buy_votes": buy_votes,
            "sell_votes": sell_votes,
            "hold_votes": hold_votes,
            "strategies": signals,
        }

