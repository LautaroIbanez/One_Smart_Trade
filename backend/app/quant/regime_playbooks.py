"""Regime-specific parameter playbooks for dynamic strategy adaptation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml
from pathlib import Path


@dataclass
class RegimePlaybook:
    """Parameter template for a specific market regime."""

    regime: str
    params: dict[str, Any]
    description: str = ""

    def get_param(self, path: str, default: Any = None) -> Any:
        """
        Get parameter value by nested path (e.g., "breakout.lookback").
        
        Args:
            path: Dot-separated path to parameter
            default: Default value if not found
            
        Returns:
            Parameter value or default
        """
        parts = path.split(".")
        current = self.params
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default
        return current

    def merge_params(self, base_params: dict[str, Any]) -> dict[str, Any]:
        """
        Merge playbook params with base params (playbook takes precedence).
        
        Args:
            base_params: Base parameters dict
            
        Returns:
            Merged parameters dict
        """
        merged = self._deep_merge(base_params.copy(), self.params)
        return merged

    @staticmethod
    def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        """Deep merge two dictionaries."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = RegimePlaybook._deep_merge(result[key], value)
            else:
                result[key] = value
        return result


class RegimePlaybookManager:
    """Manager for regime-specific parameter playbooks."""

    def __init__(
        self,
        playbooks: dict[str, RegimePlaybook] | None = None,
        playbook_dir: Path | None = None,
    ) -> None:
        """
        Initialize playbook manager.
        
        Args:
            playbooks: Dict of regime name to RegimePlaybook
            playbook_dir: Optional directory to load playbooks from YAML files
        """
        self.playbooks = playbooks or {}
        self.playbook_dir = playbook_dir
        if playbook_dir and playbook_dir.exists():
            self._load_playbooks_from_dir(playbook_dir)

    def _load_playbooks_from_dir(self, directory: Path) -> None:
        """Load playbooks from YAML files in directory."""
        for yaml_file in directory.glob("*.yaml"):
            try:
                with yaml_file.open() as f:
                    data = yaml.safe_load(f)
                    if isinstance(data, dict):
                        regime = data.get("regime", yaml_file.stem)
                        params = data.get("params", {})
                        description = data.get("description", "")
                        self.playbooks[regime] = RegimePlaybook(
                            regime=regime,
                            params=params,
                            description=description,
                        )
            except Exception as e:
                from app.core.logging import logger
                logger.warning("Failed to load playbook", extra={"file": str(yaml_file), "error": str(e)})

    def get_playbook(self, regime: str) -> RegimePlaybook | None:
        """
        Get playbook for a specific regime.
        
        Args:
            regime: Regime name (e.g., "calm", "balanced", "stress")
            
        Returns:
            RegimePlaybook or None if not found
        """
        return self.playbooks.get(regime)

    def apply_playbook(
        self,
        regime: str,
        base_params: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Apply playbook parameters to base parameters.
        
        Args:
            regime: Regime name
            base_params: Base parameters dict
            
        Returns:
            Merged parameters with playbook overrides
        """
        playbook = self.get_playbook(regime)
        if playbook:
            return playbook.merge_params(base_params)
        return base_params

    def get_default_playbooks(self) -> dict[str, RegimePlaybook]:
        """Get default playbooks for calm, balanced, and stress regimes."""
        return {
            "calm": RegimePlaybook(
                regime="calm",
                description="Low volatility, trending markets - aggressive parameters",
                params={
                    "breakout": {
                        "lookback": 15,
                        "volume_multiple": 1.3,
                    },
                    "volatility": {
                        "low_threshold": 0.15,
                        "high_threshold": 0.4,
                    },
                    "aggregate": {
                        "vector_bias": {
                            "momentum_bias_weight": 0.3,
                            "breakout_slope_weight": 0.15,
                        },
                        "buy_threshold": 0.12,
                        "sell_threshold": -0.12,
                    },
                },
            ),
            "balanced": RegimePlaybook(
                regime="balanced",
                description="Normal market conditions - standard parameters",
                params={
                    "breakout": {
                        "lookback": 20,
                        "volume_multiple": 1.5,
                    },
                    "volatility": {
                        "low_threshold": 0.2,
                        "high_threshold": 0.5,
                    },
                    "aggregate": {
                        "vector_bias": {
                            "momentum_bias_weight": 0.24,
                            "breakout_slope_weight": 0.1,
                        },
                        "buy_threshold": 0.15,
                        "sell_threshold": -0.15,
                    },
                },
            ),
            "stress": RegimePlaybook(
                regime="stress",
                description="High volatility, choppy markets - conservative parameters",
                params={
                    "breakout": {
                        "lookback": 30,
                        "volume_multiple": 2.0,
                    },
                    "volatility": {
                        "low_threshold": 0.25,
                        "high_threshold": 0.6,
                    },
                    "aggregate": {
                        "vector_bias": {
                            "momentum_bias_weight": 0.15,
                            "breakout_slope_weight": 0.05,
                        },
                        "buy_threshold": 0.18,
                        "sell_threshold": -0.18,
                    },
                },
            ),
        }

    def initialize_defaults(self) -> None:
        """Initialize with default playbooks if none are loaded."""
        if not self.playbooks:
            self.playbooks = self.get_default_playbooks()





