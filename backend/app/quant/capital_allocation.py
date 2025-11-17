"""Dynamic capital allocation based on regime probabilities."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class CapitalAllocationRules:
    """Rules for dynamic capital allocation based on regime probabilities."""

    base_size_pct: float = 1.0
    calm_multiplier: float = 1.2
    balanced_multiplier: float = 1.0
    stress_multiplier: float = 0.5
    stress_threshold: float = 0.5
    min_size_pct: float = 0.1
    max_size_pct: float = 1.5

    def calculate_position_size(
        self,
        regime_probabilities: dict[str, float],
    ) -> float:
        """
        Calculate position size based on regime probabilities.
        
        Args:
            regime_probabilities: Dict with keys like "calm", "balanced", "stress" and probabilities
            
        Returns:
            Position size as percentage of capital (0.0 to max_size_pct)
        """
        calm_prob = regime_probabilities.get("calm", 0.0)
        balanced_prob = regime_probabilities.get("balanced", 0.0)
        stress_prob = regime_probabilities.get("stress", 0.0)
        
        if stress_prob > self.stress_threshold:
            size_pct = self.base_size_pct * self.stress_multiplier
        else:
            size_pct = (
                self.base_size_pct
                * (
                    calm_prob * self.calm_multiplier
                    + balanced_prob * self.balanced_multiplier
                    + stress_prob * self.stress_multiplier
                )
            )
        
        return float(np.clip(size_pct, self.min_size_pct, self.max_size_pct))


@dataclass
class KellyAllocation:
    """Kelly criterion based allocation with regime adjustments."""

    base_kelly_fraction: float = 0.25
    calm_kelly_multiplier: float = 1.5
    stress_kelly_multiplier: float = 0.3
    stress_threshold: float = 0.5

    def calculate_position_size(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        regime_probabilities: dict[str, float],
    ) -> float:
        """
        Calculate position size using Kelly criterion adjusted by regime.
        
        Args:
            win_rate: Win rate (0.0 to 1.0)
            avg_win: Average winning trade return (as fraction, e.g., 0.02 for 2%)
            avg_loss: Average losing trade return (as absolute value, e.g., 0.01 for 1%)
            regime_probabilities: Dict with regime probabilities
            
        Returns:
            Position size as fraction of capital
        """
        if avg_loss <= 0:
            return 0.0
        
        stress_prob = regime_probabilities.get("stress", 0.0)
        calm_prob = regime_probabilities.get("calm", 0.0)
        
        win_loss_ratio = abs(avg_win / avg_loss) if avg_loss > 0 else 1.0
        kelly_fraction = (win_rate * (1 + win_loss_ratio) - 1) / win_loss_ratio
        
        if kelly_fraction <= 0:
            return 0.0
        
        if stress_prob > self.stress_threshold:
            kelly_fraction *= self.stress_kelly_multiplier
        elif calm_prob > 0.6:
            kelly_fraction *= self.calm_kelly_multiplier
        
        return float(np.clip(kelly_fraction, 0.0, self.base_kelly_fraction))


class DynamicCapitalAllocator:
    """Dynamic capital allocation system with regime-based sizing."""

    def __init__(
        self,
        rules: CapitalAllocationRules | None = None,
        use_kelly: bool = False,
        kelly_config: KellyAllocation | None = None,
    ) -> None:
        """
        Initialize dynamic capital allocator.
        
        Args:
            rules: Capital allocation rules (default: standard rules)
            use_kelly: Use Kelly criterion instead of simple multipliers
            kelly_config: Kelly allocation config (default: standard config)
        """
        self.rules = rules or CapitalAllocationRules()
        self.use_kelly = use_kelly
        self.kelly_config = kelly_config or KellyAllocation()

    def allocate(
        self,
        regime_probabilities: dict[str, float],
        *,
        win_rate: float | None = None,
        avg_win: float | None = None,
        avg_loss: float | None = None,
    ) -> float:
        """
        Allocate capital based on regime probabilities.
        
        Args:
            regime_probabilities: Dict with regime probabilities
            win_rate: Optional win rate for Kelly criterion
            avg_win: Optional average win for Kelly criterion
            avg_loss: Optional average loss for Kelly criterion
            
        Returns:
            Position size as percentage of capital
        """
        if self.use_kelly and win_rate is not None and avg_win is not None and avg_loss is not None:
            return self.kelly_config.calculate_position_size(
                win_rate,
                avg_win,
                avg_loss,
                regime_probabilities,
            )
        else:
            return self.rules.calculate_position_size(regime_probabilities)

    def get_allocation_factor(
        self,
        regime_probabilities: dict[str, float],
    ) -> float:
        """
        Get allocation factor (0.0 to 1.0) relative to base size.
        
        Args:
            regime_probabilities: Dict with regime probabilities
            
        Returns:
            Allocation factor (e.g., 0.5 means 50% of base size)
        """
        size_pct = self.rules.calculate_position_size(regime_probabilities)
        return size_pct / self.rules.base_size_pct



