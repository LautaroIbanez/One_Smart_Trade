"""Base strategy class."""
from abc import ABC, abstractmethod
from typing import Dict, Any, Literal
import pandas as pd


SignalType = Literal["BUY", "HOLD", "SELL"]


class BaseStrategy(ABC):
    """Base class for trading strategies."""

    def __init__(self, name: str):
        self.name = name
        self.historical_performance: Dict[str, Any] = {}

    @abstractmethod
    def generate_signal(self, df: pd.DataFrame, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """Generate trading signal based on data and indicators."""
        pass

    def calculate_confidence(self, signal_data: Dict[str, Any]) -> float:
        """Calculate confidence score for the signal (0-100)."""
        return 50.0  # Default confidence

    def update_performance(self, result: Dict[str, Any]):
        """Update historical performance metrics."""
        if "win_rate" not in self.historical_performance:
            self.historical_performance["win_rate"] = 0.0
            self.historical_performance["total_trades"] = 0
            self.historical_performance["winning_trades"] = 0

        self.historical_performance["total_trades"] += 1
        if result.get("profit", 0) > 0:
            self.historical_performance["winning_trades"] += 1

        self.historical_performance["win_rate"] = (
            self.historical_performance["winning_trades"] / self.historical_performance["total_trades"] * 100
        )

