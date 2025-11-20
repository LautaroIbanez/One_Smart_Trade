"""Reproducible ruin simulation with seed control and full distribution storage."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from app.core.logging import logger


@dataclass
class RuinSimulationResult:
    """Result of ruin simulation with full distribution."""

    ruin_probability: float
    distribution: list[float] = field(default_factory=list)  # Full distribution of final equity
    paths: list[list[float]] = field(default_factory=list)  # Sample equity paths
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "ruin_probability": self.ruin_probability,
            "distribution_summary": {
                "mean": float(np.mean(self.distribution)) if self.distribution else 0.0,
                "std": float(np.std(self.distribution)) if self.distribution else 0.0,
                "p5": float(np.percentile(self.distribution, 5)) if self.distribution else 0.0,
                "p50": float(np.percentile(self.distribution, 50)) if self.distribution else 0.0,
                "p95": float(np.percentile(self.distribution, 95)) if self.distribution else 0.0,
            },
            "n_paths": len(self.paths),
            "metadata": self.metadata,
        }


def monte_carlo_ruin(
    returns_per_trade: list[float] | pd.Series,
    *,
    equity: float = 10000.0,
    ruin_threshold: float = 0.5,  # 50% of initial equity
    n_paths: int = 10000,
    horizon_trades: int | None = None,
    seed: int | None = None,
    store_distribution: bool = True,
    store_sample_paths: bool = False,
    n_sample_paths: int = 100,
) -> RuinSimulationResult:
    """
    Run reproducible Monte Carlo ruin simulation.

    Args:
        returns_per_trade: Returns per trade (as fractions, e.g., 0.01 for 1%)
        equity: Initial equity
        ruin_threshold: Ruin threshold as fraction of initial equity (default: 0.5 = 50%)
        n_paths: Number of Monte Carlo paths
        horizon_trades: Number of trades to simulate (default: len(returns_per_trade))
        seed: Random seed for reproducibility
        store_distribution: Whether to store full distribution
        store_sample_paths: Whether to store sample equity paths
        n_sample_paths: Number of sample paths to store

    Returns:
        RuinSimulationResult with probability and distribution
    """
    if isinstance(returns_per_trade, list):
        returns = pd.Series(returns_per_trade)
    else:
        returns = returns_per_trade

    if len(returns) == 0:
        return RuinSimulationResult(ruin_probability=0.0, metadata={"error": "empty_returns"})

    horizon = horizon_trades or len(returns)
    ruin_threshold_equity = equity * ruin_threshold

    # Initialize RNG with seed
    rng = np.random.default_rng(seed)

    # Run simulations
    final_equities = []
    sample_paths = []
    ruin_count = 0

    for path_idx in range(n_paths):
        # Sample returns with replacement
        sample_indices = rng.integers(0, len(returns), size=horizon)
        path_returns = returns.iloc[sample_indices].values

        # Simulate equity path
        equity_path = [equity]
        for ret in path_returns:
            new_equity = equity_path[-1] * (1 + ret)
            equity_path.append(new_equity)

            # Check for ruin
            if new_equity <= ruin_threshold_equity:
                ruin_count += 1
                break

        final_equity = equity_path[-1]
        final_equities.append(final_equity)

        # Store sample paths
        if store_sample_paths and path_idx < n_sample_paths:
            sample_paths.append(equity_path)

    # Calculate ruin probability
    ruin_probability = ruin_count / n_paths

    # Build result
    result = RuinSimulationResult(
        ruin_probability=ruin_probability,
        distribution=final_equities if store_distribution else [],
        paths=sample_paths if store_sample_paths else [],
        metadata={
            "n_paths": n_paths,
            "horizon_trades": horizon,
            "initial_equity": equity,
            "ruin_threshold": ruin_threshold,
            "ruin_threshold_equity": ruin_threshold_equity,
            "seed": seed,
            "n_trades_available": len(returns),
        },
    )

    return result





