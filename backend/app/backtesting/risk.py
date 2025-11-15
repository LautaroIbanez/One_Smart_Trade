"""Monte Carlo risk simulations for drawdowns, losing streaks, and ruin probability."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
import pandas as pd


@dataclass(slots=True)
class RiskSimulationConfig:
    """Configuration parameters for risk simulations."""

    trials: int = 5000
    horizon_trades: int | None = None
    ruin_threshold: float = 0.5
    streak_threshold: int = 5


def simulate_drawdown_paths(
    equity_curve: Sequence[float],
    *,
    trials: int,
    horizon_trades: int,
    ruin_threshold: float,
) -> dict[str, float]:
    """
    Simulate equity paths using a log-normal random walk to estimate drawdown extremes and ruin probability.
    Returns percentage drawdowns (positive values) and probability of breaching the ruin threshold.
    """
    if len(equity_curve) < 5:
        return {}

    series = np.asarray(equity_curve, dtype=float)
    returns = np.diff(np.log(series))
    returns = returns[np.isfinite(returns)]
    if returns.size < 5:
        return {}

    mean = float(returns.mean())
    std = float(returns.std(ddof=1))
    if np.isclose(std, 0.0):
        return {}

    horizon = max(int(horizon_trades), 1)
    rng = np.random.default_rng()
    shocks = rng.normal(loc=mean, scale=std, size=(trials, horizon))
    simulated = np.exp(np.cumsum(shocks, axis=1))
    simulated = np.insert(simulated, 0, 1.0, axis=1)

    peak = np.maximum.accumulate(simulated, axis=1)
    drawdowns = 1.0 - (simulated / peak)
    worst_dd = np.percentile(drawdowns.max(axis=1) * 100.0, [50, 95, 99])
    ruin_prob = float((simulated[:, -1] <= ruin_threshold).mean())

    return {
        "median_worst_dd_pct": round(float(worst_dd[0]), 2),
        "p95_worst_dd_pct": round(float(worst_dd[1]), 2),
        "p99_worst_dd_pct": round(float(worst_dd[2]), 2),
        "ruin_prob": round(ruin_prob, 4),
    }


def simulate_losing_streaks(
    trade_returns: Sequence[float],
    *,
    trials: int,
    horizon_trades: int,
    streak_threshold: int,
) -> dict[str, float]:
    """Bootstrap trade returns to estimate losing streak duration risk."""
    if len(trade_returns) < 5:
        return {}

    returns = np.asarray(trade_returns, dtype=float)
    returns = returns[np.isfinite(returns)]
    if returns.size < 5:
        return {}

    horizon = max(int(horizon_trades), 1)
    streak_cutoff = max(int(streak_threshold), 1)

    rng = np.random.default_rng()
    samples = rng.choice(returns, size=(trials, horizon), replace=True)
    losing_mask = samples <= 0.0

    longest_streaks = np.fromiter((_max_consecutive_true(row) for row in losing_mask), dtype=int, count=trials)

    percentiles = np.percentile(longest_streaks, [50, 95, 99])
    prob_long_streak = float((longest_streaks >= streak_cutoff).mean())

    return {
        "median_losing_streak": int(round(percentiles[0])),
        "p95_losing_streak": int(round(percentiles[1])),
        "p99_losing_streak": int(round(percentiles[2])),
        "prob_streak_ge_threshold": round(prob_long_streak, 4),
        "streak_threshold": streak_cutoff,
    }


def run_risk_simulations(
    equity_curve: Sequence[float],
    trade_returns: Sequence[float],
    config: RiskSimulationConfig | None = None,
) -> dict[str, float]:
    """Run Monte Carlo simulations to produce a consolidated risk profile."""
    cfg = config or RiskSimulationConfig()
    horizon = cfg.horizon_trades or max(len(equity_curve), len(trade_returns), 1)

    drawdown_stats = simulate_drawdown_paths(
        equity_curve,
        trials=cfg.trials,
        horizon_trades=horizon,
        ruin_threshold=cfg.ruin_threshold,
    )
    streak_stats = simulate_losing_streaks(
        trade_returns,
        trials=cfg.trials,
        horizon_trades=horizon,
        streak_threshold=cfg.streak_threshold,
    )

    risk_profile: dict[str, float] = {}
    risk_profile.update(drawdown_stats)
    risk_profile.update(streak_stats)

    if not risk_profile:
        return {}

    risk_profile["trials"] = cfg.trials
    risk_profile["horizon_trades"] = horizon
    risk_profile["ruin_threshold"] = cfg.ruin_threshold
    risk_profile["streak_risk_threshold"] = cfg.streak_threshold
    return risk_profile


def _max_consecutive_true(values: np.ndarray) -> int:
    """Return the maximum number of consecutive True values in a boolean array."""
    max_run = 0
    current_run = 0
    for is_true in values:
        if bool(is_true):
            current_run += 1
            if current_run > max_run:
                max_run = current_run
        else:
            current_run = 0
    return max_run


class RuinSimulator:
    """
    Monte Carlo simulation for ruin probability based on win rate and payoff ratio.
    
    Uses historical trade parameters (win_rate, avg_win, avg_loss) to estimate
    the probability of reaching a capital threshold (e.g., -50%).
    """

    def estimate(
        self,
        win_rate: float,
        payoff_ratio: float,
        horizon: int = 250,
        threshold: float = 0.5,
        trials: int = 5000,
    ) -> float:
        """
        Estimate ruin probability using Monte Carlo simulation.
        
        Formula: outcomes are randomly sampled as wins (payoff_ratio) or losses (-1.0)
        based on win_rate. Ruin occurs when equity path touches threshold.
        
        The simulation models each trade as:
        - Win: +payoff_ratio (e.g., +2.0 means win is 2x the loss)
        - Loss: -1.0 (standardized loss)
        
        Equity paths are calculated as cumulative sum of outcomes.
        Ruin occurs when the minimum equity path value reaches log(threshold).
        
        Args:
            win_rate: Probability of winning trade (0.0 to 1.0)
            payoff_ratio: Average win / Average loss (e.g., 2.0 means wins are 2x losses)
            horizon: Number of trades to simulate (default: 250)
            threshold: Ruin threshold as fraction of initial capital (default: 0.5 for -50%)
            trials: Number of Monte Carlo trials (default: 5000)
            
        Returns:
            Probability of ruin (0.0 to 1.0)
        """
        if win_rate <= 0 or win_rate >= 1 or payoff_ratio <= 0:
            return 1.0 if win_rate <= 0 else 0.0
        
        if horizon <= 0 or trials <= 0:
            return 0.0
        
        rng = np.random.default_rng()
        
        # Generate random outcomes: wins (payoff_ratio) or losses (-1.0)
        # Each outcome represents a standardized return (positive for wins, negative for losses)
        random_values = rng.random(size=(trials, horizon))
        outcomes = np.where(random_values < win_rate, payoff_ratio, -1.0)
        
        # Calculate cumulative equity paths (standardized)
        # Each path starts at 0, accumulates wins and losses
        # Positive values = above initial, negative values = below initial
        equity_paths = outcomes.cumsum(axis=1)
        
        # Check if any path touches threshold
        # Threshold is in log space (e.g., log(0.5) for -50% from initial)
        # Convert threshold to standardized scale: log(threshold) represents the log-space threshold
        # For simplicity, we interpret threshold as a multiplier: 0.5 means 50% of initial
        # In standardized returns, we check if path goes below log(threshold)
        threshold_log = np.log(threshold) if threshold > 0 else float("-inf")
        ruin = (equity_paths.min(axis=1) <= threshold_log).mean()
        
        return float(round(ruin, 4))

    def estimate_from_trades(
        self,
        trades: list[dict[str, Any]] | pd.DataFrame,
        *,
        horizon: int = 250,
        threshold: float = 0.5,
        trials: int = 5000,
    ) -> dict[str, Any]:
        """
        Estimate ruin probability using real trade history parameters.
        
        Calculates win_rate and payoff_ratio from trade history, then runs simulation.
        
        Args:
            trades: List of trade dicts or DataFrame with trade data
            horizon: Number of trades to simulate (default: 250)
            threshold: Ruin threshold as fraction of initial capital (default: 0.5 for -50%)
            trials: Number of Monte Carlo trials (default: 5000)
            
        Returns:
            Dict with ruin_probability, win_rate, payoff_ratio, and parameters
        """
        if isinstance(trades, list):
            if not trades:
                return {"ruin_probability": 0.0, "win_rate": 0.0, "payoff_ratio": 0.0}
            trades_df = pd.DataFrame(trades)
        else:
            trades_df = trades.copy()
        
        if trades_df.empty:
            return {"ruin_probability": 0.0, "win_rate": 0.0, "payoff_ratio": 0.0}
        
        # Calculate win rate
        if "pnl" in trades_df.columns:
            winning_trades = trades_df[trades_df["pnl"] > 0]
            losing_trades = trades_df[trades_df["pnl"] < 0]
            win_rate = len(winning_trades) / len(trades_df) if len(trades_df) > 0 else 0.0
        elif "return_pct" in trades_df.columns:
            winning_trades = trades_df[trades_df["return_pct"] > 0]
            losing_trades = trades_df[trades_df["return_pct"] < 0]
            win_rate = len(winning_trades) / len(trades_df) if len(trades_df) > 0 else 0.0
        else:
            return {"ruin_probability": 0.0, "win_rate": 0.0, "payoff_ratio": 0.0}
        
        # Calculate payoff ratio (avg_win / avg_loss)
        if "pnl" in trades_df.columns:
            avg_win = winning_trades["pnl"].mean() if len(winning_trades) > 0 else 0.0
            avg_loss = abs(losing_trades["pnl"].mean()) if len(losing_trades) > 0 else 1.0
        elif "return_pct" in trades_df.columns:
            avg_win = winning_trades["return_pct"].mean() if len(winning_trades) > 0 else 0.0
            avg_loss = abs(losing_trades["return_pct"].mean()) if len(losing_trades) > 0 else 1.0
        else:
            return {"ruin_probability": 0.0, "win_rate": 0.0, "payoff_ratio": 0.0}
        
        if avg_loss == 0:
            payoff_ratio = 0.0
        else:
            payoff_ratio = avg_win / avg_loss
        
        # Run simulation
        ruin_prob = self.estimate(
            win_rate=win_rate,
            payoff_ratio=payoff_ratio,
            horizon=horizon,
            threshold=threshold,
            trials=trials,
        )
        
        return {
            "ruin_probability": ruin_prob,
            "win_rate": round(win_rate, 4),
            "payoff_ratio": round(payoff_ratio, 4),
            "avg_win": round(avg_win, 4),
            "avg_loss": round(avg_loss, 4),
            "total_trades": len(trades_df),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "horizon": horizon,
            "threshold": threshold,
            "trials": trials,
        }

    def estimate_with_multiple_thresholds(
        self,
        win_rate: float,
        payoff_ratio: float,
        thresholds: list[float] | None = None,
        horizon: int = 250,
        trials: int = 5000,
    ) -> dict[str, float]:
        """
        Estimate ruin probability for multiple thresholds.
        
        Args:
            win_rate: Probability of winning trade
            payoff_ratio: Average win / Average loss
            thresholds: List of ruin thresholds (default: [0.9, 0.8, 0.7, 0.5, 0.3])
            horizon: Number of trades to simulate
            trials: Number of Monte Carlo trials
            
        Returns:
            Dict mapping threshold to ruin probability
        """
        if thresholds is None:
            thresholds = [0.9, 0.8, 0.7, 0.5, 0.3]  # -10%, -20%, -30%, -50%, -70%
        
        results = {}
        for threshold in thresholds:
            prob = self.estimate(
                win_rate=win_rate,
                payoff_ratio=payoff_ratio,
                horizon=horizon,
                threshold=threshold,
                trials=trials,
            )
            results[f"ruin_prob_{int((1 - threshold) * 100)}pct"] = prob
        
        return results


__all__ = [
    "RiskSimulationConfig",
    "RuinSimulator",
    "run_risk_simulations",
    "simulate_drawdown_paths",
    "simulate_losing_streaks",
]


