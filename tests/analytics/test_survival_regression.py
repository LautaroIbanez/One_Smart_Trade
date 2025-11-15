from __future__ import annotations

import numpy as np
import pandas as pd

from app.analytics.ruin import SurvivalSimulator


def test_survival_simulator_is_seed_reproducible():
    # Fixed synthetic returns (monthly): slight positive drift with noise
    rng = np.random.default_rng(7)
    series = pd.Series(rng.normal(loc=0.01, scale=0.03, size=240))  # 20 years

    sim_a = SurvivalSimulator(trials=2000, horizon_months=36, ruin_threshold=0.7, seed=123)
    sim_b = SurvivalSimulator(trials=2000, horizon_months=36, ruin_threshold=0.7, seed=123)
    ra = sim_a.monte_carlo(series)
    rb = sim_b.monte_carlo(series)
    assert ra["ruin_probability"] == rb["ruin_probability"]
    assert ra["p50_equity"] == rb["p50_equity"]


def test_survival_simulator_regression_tolerance():
    # Establish a snapshot target under controlled seed and parameters
    series = pd.Series([0.0, 0.02, -0.01, 0.03, -0.02, 0.015] * 40)  # 240 months
    sim = SurvivalSimulator(trials=5000, horizon_months=36, ruin_threshold=0.7, seed=999)
    res = sim.monte_carlo(series)
    # Snapshot expectations may drift slightly with numpy changes; use tight tolerance
    expected_ruin = 0.0176
    assert abs(res["ruin_probability"] - expected_ruin) < 0.005, f"Ruin prob regression: {res['ruin_probability']}"


