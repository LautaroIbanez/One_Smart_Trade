"""Objective definitions for evaluating backtest performance."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ObjectiveConfig:
    """Configuration values for risk-aware objective scoring."""

    name: str = "calmar_under_drawdown"
    target_metric: str = "calmar"
    max_drawdown_limit: float = 15.0
    min_improvement: float = 0.05


class Objective(Protocol):
    """Interface for objective functions used to compare backtests."""

    def score(self, metrics: dict[str, float]) -> float:
        """Return the target metric score for the provided metrics."""

    def is_valid(self, metrics: dict[str, float]) -> bool:
        """Return whether the metrics satisfy the objective constraints."""


@dataclass
class CalmarUnderDrawdown(Objective):
    """Objective prioritizing Calmar ratio while respecting drawdown limits."""

    config: ObjectiveConfig = ObjectiveConfig()

    def score(self, metrics: dict[str, float]) -> float:
        """Return the Calmar ratio if valid, otherwise negative infinity."""
        if not self.is_valid(metrics):
            return float("-inf")
        return metrics.get(self.config.target_metric, 0.0)

    def is_valid(self, metrics: dict[str, float]) -> bool:
        """Validate that max drawdown stays within the configured limit."""
        return metrics.get("max_drawdown", 100.0) <= self.config.max_drawdown_limit








