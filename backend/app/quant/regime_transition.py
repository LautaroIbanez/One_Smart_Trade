"""Regime transition detection with exponential moving average filtering."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class RegimeTransitionConfig:
    """Configuration for regime transition detection."""

    ema_alpha: float = 0.3
    transition_threshold: float = 0.6
    min_observations: int = 3
    confirmation_periods: int = 2


class RegimeTransitionDetector:
    """Detect persistent regime changes using exponential moving average."""

    def __init__(
        self,
        config: RegimeTransitionConfig | None = None,
    ) -> None:
        """
        Initialize regime transition detector.
        
        Args:
            config: Transition detection configuration
        """
        self.config = config or RegimeTransitionConfig()
        self.regime_history: deque[dict[str, float]] = deque(maxlen=100)
        self.ema_probabilities: dict[str, float] = {}
        self.current_regime: str | None = None

    def update(
        self,
        regime_probabilities: dict[str, float],
    ) -> dict[str, Any]:
        """
        Update detector with new regime probabilities and check for transitions.
        
        Args:
            regime_probabilities: Current regime probabilities
            
        Returns:
            Dict with transition status and details
        """
        self.regime_history.append(regime_probabilities.copy())
        
        if len(self.regime_history) < self.config.min_observations:
            return {
                "transition_detected": False,
                "current_regime": None,
                "reason": "insufficient_data",
            }
        
        dominant_regime = max(regime_probabilities.items(), key=lambda x: x[1])
        regime_name, proba = dominant_regime
        
        for regime in ["calm", "balanced", "stress"]:
            prob = regime_probabilities.get(regime, 0.0)
            
            if regime not in self.ema_probabilities:
                self.ema_probabilities[regime] = prob
            else:
                self.ema_probabilities[regime] = (
                    self.config.ema_alpha * prob + (1 - self.config.ema_alpha) * self.ema_probabilities[regime]
                )
        
        ema_proba = self.ema_probabilities.get(regime_name, 0.0)
        
        transition_detected = False
        transition_reason = None
        
        if ema_proba >= self.config.transition_threshold:
            if self.current_regime != regime_name:
                transition_detected = True
                transition_reason = f"persistent_transition_to_{regime_name}"
                self.current_regime = regime_name
        elif self.current_regime is None and ema_proba >= self.config.transition_threshold * 0.8:
            self.current_regime = regime_name
        
        return {
            "transition_detected": transition_detected,
            "current_regime": self.current_regime,
            "dominant_regime": regime_name,
            "dominant_probability": float(proba),
            "ema_probability": float(ema_proba),
            "ema_probabilities": {k: float(v) for k, v in self.ema_probabilities.items()},
            "raw_probabilities": regime_probabilities,
            "reason": transition_reason or "no_transition",
        }

    def get_persistent_regime(self) -> str | None:
        """
        Get the current persistent regime (if EMA probability > threshold).
        
        Returns:
            Regime name or None
        """
        for regime, ema_proba in self.ema_probabilities.items():
            if ema_proba >= self.config.transition_threshold:
                return regime
        return None

    def get_weighted_regime(
        self,
        weights: dict[str, float] | None = None,
    ) -> str:
        """
        Get weighted regime based on EMA probabilities.
        
        Args:
            weights: Optional weights for each regime (default: equal weights)
            
        Returns:
            Weighted regime name
        """
        if weights is None:
            weights = {"calm": 1.0, "balanced": 1.0, "stress": 1.0}
        
        weighted_proba = {
            regime: self.ema_probabilities.get(regime, 0.0) * weights.get(regime, 1.0)
            for regime in ["calm", "balanced", "stress"]
        }
        
        return max(weighted_proba.items(), key=lambda x: x[1])[0]

    def reset(self) -> None:
        """Reset detector state."""
        self.regime_history.clear()
        self.ema_probabilities.clear()
        self.current_regime = None


class RegimeTransitionManager:
    """Manage regime transitions and playbook switching."""

    def __init__(
        self,
        detector: RegimeTransitionDetector | None = None,
        playbook_manager: Any | None = None,
    ) -> None:
        """
        Initialize regime transition manager.
        
        Args:
            detector: Regime transition detector
            playbook_manager: RegimePlaybookManager instance
        """
        from app.quant.regime_playbooks import RegimePlaybookManager
        
        self.detector = detector or RegimeTransitionDetector()
        self.playbook_manager = playbook_manager or RegimePlaybookManager()
        self.playbook_manager.initialize_defaults()
        self.last_applied_regime: str | None = None

    def process_transition(
        self,
        regime_probabilities: dict[str, float],
        base_params: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Process regime transition and return appropriate parameters.
        
        Args:
            regime_probabilities: Current regime probabilities
            base_params: Base parameters to merge with playbook
            
        Returns:
            Dict with updated params, transition info, and playbook applied
        """
        transition_info = self.detector.update(regime_probabilities)
        
        if transition_info["transition_detected"]:
            new_regime = transition_info["current_regime"]
            if new_regime and new_regime != self.last_applied_regime:
                updated_params = self.playbook_manager.apply_playbook(new_regime, base_params)
                self.last_applied_regime = new_regime
                
                return {
                    "params": updated_params,
                    "transition_detected": True,
                    "regime": new_regime,
                    "transition_info": transition_info,
                    "playbook_applied": new_regime,
                }
        
        if self.detector.current_regime:
            updated_params = self.playbook_manager.apply_playbook(self.detector.current_regime, base_params)
            return {
                "params": updated_params,
                "transition_detected": False,
                "regime": self.detector.current_regime,
                "transition_info": transition_info,
                "playbook_applied": self.detector.current_regime,
            }
        
        return {
            "params": base_params,
            "transition_detected": False,
            "regime": None,
            "transition_info": transition_info,
            "playbook_applied": None,
        }



