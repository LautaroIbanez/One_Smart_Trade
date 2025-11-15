from __future__ import annotations

import numpy as np
import pandas as pd

from app.analytics.ruin import SurvivalSimulator


def test_monte_carlo_convergence_variance_under_5_percent():
    # Synthetic monthly returns around 1% mean, 5% std
    rng = np.random.default_rng(42)
    base = rng.normal(loc=0.01, scale=0.05, size=120)  # 10 years
    series = pd.Series(base)

    # Run 100 independent estimates and measure coefficient of variation (std/mean)
    estimates = []
    for seed in range(100):
        sim = SurvivalSimulator(trials=1000, horizon_months=36, ruin_threshold=0.7)
        # Each run draws its own randomness
        estimates.append(sim.monte_carlo(series)["ruin_probability"])
    estimates = np.asarray(estimates)
    mean_est = float(estimates.mean())
    std_est = float(estimates.std(ddof=1))
    cv = std_est / (mean_est + 1e-9)
    assert cv < 0.05, f"Coefficient of variation too high: {cv:.4f}"


