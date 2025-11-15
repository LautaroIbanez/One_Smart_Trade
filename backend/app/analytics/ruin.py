from __future__ import annotations

import numpy as np
import pandas as pd


class SurvivalSimulator:
    def __init__(self, trials: int = 10_000, horizon_months: int = 36, ruin_threshold: float = 0.7, seed: int | None = None):
        self.trials = trials
        self.horizon = horizon_months
        self.threshold = ruin_threshold
        self.seed = seed

    def monte_carlo(self, monthly_returns: pd.Series) -> dict[str, float]:
        if monthly_returns.empty:
            return {
                "ruin_probability": 0.0,
                "median_drawdown": 0.0,
                "p10_equity": 1.0,
                "p50_equity": 1.0,
                "p90_equity": 1.0,
            }
        rng = np.random.default_rng(self.seed)
        samples = rng.choice(monthly_returns.values, size=(self.trials, self.horizon), replace=True)
        equity_paths = np.cumprod(1 + samples, axis=1)
        path_mins = equity_paths.min(axis=1)
        ruin_prob = float((path_mins <= self.threshold).mean())
        median_drawdown = float(1 - np.quantile(path_mins, 0.5))
        return {
            "ruin_probability": round(ruin_prob, 4),
            "median_drawdown": round(median_drawdown, 4),
            "p10_equity": float(np.quantile(equity_paths[:, -1], 0.1)),
            "p50_equity": float(np.quantile(equity_paths[:, -1], 0.5)),
            "p90_equity": float(np.quantile(equity_paths[:, -1], 0.9)),
        }


