"""Calculate professional backtesting metrics."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.backtesting.advanced_metrics import MetricsReport
from app.backtesting.execution_metrics import ExecutionMetrics
from app.backtesting.risk import RuinSimulator, run_risk_simulations
from app.backtesting.ruin_simulation import monte_carlo_ruin


def calculate_metrics(backtest_result: dict[str, Any], **kwargs) -> dict[str, float]:
    """Calculate comprehensive backtesting metrics."""
    trades = backtest_result.get("trades", [])
    equity_curve = backtest_result.get("equity_curve", [])
    initial_capital = backtest_result.get("initial_capital", 10000.0)
    final_capital = backtest_result.get("final_capital", initial_capital)

    if not trades:
        return {
            "cagr": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
            "calmar": 0.0,
            "total_return": 0.0,
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
        }

    df_trades = pd.DataFrame(trades)
    returns = df_trades["return_pct"].values

    # Total return and CAGR
    total_return = ((final_capital - initial_capital) / initial_capital) * 100
    days = (pd.to_datetime(backtest_result["end_date"]) - pd.to_datetime(backtest_result["start_date"])).days
    years = days / 365.25
    cagr = ((final_capital / initial_capital) ** (1 / years) - 1) * 100 if years > 0 else 0.0

    # Sharpe Ratio (annualized, assuming 252 trading days)
    if len(returns) > 1:
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        sharpe = (mean_return / std_return) * np.sqrt(252) if std_return > 0 else 0.0
    else:
        sharpe = 0.0

    # Sortino Ratio (only downside deviation)
    downside_returns = returns[returns < 0]
    if len(downside_returns) > 0:
        downside_std = np.std(downside_returns)
        sortino = (np.mean(returns) / downside_std) * np.sqrt(252) if downside_std > 0 else 0.0
    else:
        sortino = sharpe if sharpe > 0 else 0.0

    # Max Drawdown
    equity_series = pd.Series(equity_curve)
    running_max = equity_series.expanding().max()
    drawdown = ((equity_series - running_max) / running_max) * 100
    max_drawdown = abs(drawdown.min()) if not drawdown.empty else 0.0

    # Win Rate
    winning_trades = len(df_trades[df_trades["pnl"] > 0])
    losing_trades = len(df_trades[df_trades["pnl"] < 0])
    total_trades = len(df_trades)
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

    # Profit Factor
    gross_profit = df_trades[df_trades["pnl"] > 0]["pnl"].sum()
    gross_loss = abs(df_trades[df_trades["pnl"] < 0]["pnl"].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

    # Expectancy
    avg_win = df_trades[df_trades["pnl"] > 0]["pnl"].mean() if winning_trades > 0 else 0.0
    avg_loss = df_trades[df_trades["pnl"] < 0]["pnl"].mean() if losing_trades > 0 else 0.0
    win_prob = winning_trades / total_trades if total_trades > 0 else 0.0
    loss_prob = losing_trades / total_trades if total_trades > 0 else 0.0
    expectancy = (avg_win * win_prob) + (avg_loss * loss_prob)

    # Calmar Ratio
    calmar = (cagr / max_drawdown) if max_drawdown > 0 else 0.0

    # Rolling metrics (monthly and quarterly)
    rolling_monthly = _calculate_rolling_metrics(df_trades, equity_curve, window_days=30)
    rolling_quarterly = _calculate_rolling_metrics(df_trades, equity_curve, window_days=90)
    risk_profile = run_risk_simulations(equity_curve, returns.tolist())
    longest_streak = _longest_losing_streak(df_trades)
    
    # Approximate periodic returns and negatives using fixed windows (no timestamps available here)
    equity_series = pd.Series(equity_curve)
    approx_monthly = _approximate_period_returns(equity_series, window=30)
    approx_quarterly = _approximate_period_returns(equity_series, window=90)
    monthly_negative_pct = float((approx_monthly < 0).mean()) if not approx_monthly.empty else 0.0
    
    # Risk of ruin using RuinSimulator (based on win rate and payoff ratio)
    ruin_simulator = RuinSimulator()
    ruin_results = ruin_simulator.estimate_from_trades(
        df_trades,
        horizon=250,
        threshold=0.5,  # -50% of initial capital
        trials=5000,
    )
    risk_of_ruin = ruin_results.get("ruin_probability", 0.0)
    
    # Add additional ruin metrics for multiple thresholds
    win_rate_decimal = ruin_results.get("win_rate", 0.0)
    payoff_ratio = ruin_results.get("payoff_ratio", 0.0)
    ruin_multiple_thresholds = ruin_simulator.estimate_with_multiple_thresholds(
        win_rate=win_rate_decimal,
        payoff_ratio=payoff_ratio,
        horizon=250,
        trials=5000,
    )

    metrics_dict = {
        "cagr": round(cagr, 2),
        "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2),
        "max_drawdown": round(max_drawdown, 2),
        "win_rate": round(win_rate, 2),
        "profit_factor": round(profit_factor, 2),
        "expectancy": round(expectancy, 2),
        "calmar": round(calmar, 2),
        "total_return": round(total_return, 2),
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "rolling_monthly": rolling_monthly,
        "rolling_quarterly": rolling_quarterly,
        "risk_profile": risk_profile or None,
        "longest_losing_streak": longest_streak,
        "risk_of_ruin": round(risk_of_ruin, 4),
        "ruin_simulation": {
            **ruin_results,
            "ruin_multiple_thresholds": ruin_multiple_thresholds,
        },
        # Periodic approximations for UI and filters
        "periodic_returns_approx": {
            "monthly": approx_monthly.round(6).tolist(),
            "quarterly": approx_quarterly.round(6).tolist(),
        },
        "negative_month_prob_approx": round(monthly_negative_pct, 4),
    }
    
    # Add tracking error metrics if available
    tracking_error = backtest_result.get("tracking_error")
    if tracking_error and isinstance(tracking_error, dict):
        metrics_dict["tracking_error_metrics"] = {
            "mean_deviation": tracking_error.get("mean_deviation", 0.0),
            "max_divergence": tracking_error.get("max_divergence", 0.0),
            "tracking_sharpe": tracking_error.get("tracking_sharpe", 0.0),
            "rmse": tracking_error.get("rmse", 0.0),
            "correlation": tracking_error.get("correlation", 0.0),
            "max_drawdown_divergence": tracking_error.get("max_drawdown_divergence", 0.0),
            "cumulative_tracking_error": tracking_error.get("cumulative_tracking_error", 0.0),
            "p95_divergence": tracking_error.get("p95_divergence", 0.0),
            "p99_divergence": tracking_error.get("p99_divergence", 0.0),
        }
    
    # Add advanced metrics report if returns_per_period available
    returns_per_period = backtest_result.get("returns_per_period", {})
    if returns_per_period:
        try:
            # Use monthly returns if available, otherwise daily
            returns_series = returns_per_period.get("monthly") or returns_per_period.get("daily") or []
            if returns_series:
                equity_realistic = backtest_result.get("equity_realistic", backtest_result.get("equity_curve", []))
                days = (pd.to_datetime(backtest_result["end_date"]) - pd.to_datetime(backtest_result["start_date"])).days
                
                advanced_report = MetricsReport.from_returns(
                    returns_series,
                    equity_curve=equity_realistic if equity_realistic else None,
                    initial_capital=initial_capital,
                    total_days=days,
                    bootstrap_trials=5000,
                    seed=backtest_result.get("seed"),
                )
                
                # Merge advanced metrics
                metrics_dict.update(advanced_report.metrics)
                metrics_dict["confidence_intervals"] = advanced_report.confidence_intervals
                metrics_dict["advanced_metrics"] = advanced_report.to_dict()
        except Exception as exc:
            logger.warning("Failed to calculate advanced metrics", extra={"error": str(exc)})

    # Add execution metrics if provided
    execution_metrics = kwargs.get("execution_metrics")
    if execution_metrics and isinstance(execution_metrics, ExecutionMetrics):
        metrics_dict["execution_friction"] = {
            "total_orders": execution_metrics.total_orders,
            "filled_orders": execution_metrics.filled_orders,
            "partially_filled_orders": execution_metrics.partially_filled_orders,
            "cancelled_orders": execution_metrics.cancelled_orders,
            "no_trades": execution_metrics.no_trades,
            "fill_rate": round(execution_metrics.fill_rate, 4),
            "partial_fill_rate": round(execution_metrics.partial_fill_rate, 4),
            "cancel_ratio": round(execution_metrics.cancel_ratio, 4),
            "no_trade_ratio": round(execution_metrics.no_trade_ratio, 4),
            "total_qty": round(execution_metrics.total_qty, 4),
            "filled_qty": round(execution_metrics.filled_qty, 4),
            "cancelled_qty": round(execution_metrics.cancelled_qty, 4),
            "qty_fill_rate": round(execution_metrics.qty_fill_rate, 4),
            "avg_wait_bars": round(execution_metrics.avg_wait_bars, 2),
            "median_wait_bars": round(execution_metrics.median_wait_bars, 2),
            "p95_wait_bars": round(execution_metrics.p95_wait_bars, 2),
            "avg_slippage_bps": round(execution_metrics.avg_slippage_bps, 2),
            "median_slippage_bps": round(execution_metrics.median_slippage_bps, 2),
            "p95_slippage_bps": round(execution_metrics.p95_slippage_bps, 2),
            "opportunity_cost": round(execution_metrics.opportunity_cost, 2),
            "no_trade_events_count": len(execution_metrics.no_trade_events),
        }
    
    return metrics_dict


def _calculate_rolling_metrics(trades_df: pd.DataFrame, equity_curve: list[float], window_days: int) -> dict[str, Any]:
    """Calculate rolling metrics over a window."""
    if trades_df.empty or len(equity_curve) < 2:
        return {"avg_return": 0.0, "avg_sharpe": 0.0, "max_dd": 0.0}

    # Simplified: use last N trades as proxy for window
    window_trades = min(window_days // 7, len(trades_df))  # Approximate
    if window_trades < 1:
        return {"avg_return": 0.0, "avg_sharpe": 0.0, "max_dd": 0.0}

    recent_trades = trades_df.tail(window_trades)
    recent_returns = recent_trades["return_pct"].values if len(recent_trades) > 0 else np.array([])

    avg_return = float(np.mean(recent_returns)) if len(recent_returns) > 0 else 0.0
    std_return = float(np.std(recent_returns)) if len(recent_returns) > 1 else 0.0
    avg_sharpe = (avg_return / std_return * np.sqrt(252)) if std_return > 0 else 0.0

    recent_equity = equity_curve[-window_trades:] if len(equity_curve) >= window_trades else equity_curve
    equity_series = pd.Series(recent_equity)
    running_max = equity_series.expanding().max()
    drawdown = ((equity_series - running_max) / running_max) * 100
    max_dd = abs(float(drawdown.min())) if not drawdown.empty else 0.0

    return {
        "avg_return": round(avg_return, 2),
        "avg_sharpe": round(avg_sharpe, 2),
        "max_dd": round(max_dd, 2),
    }


def _longest_losing_streak(trades_df: pd.DataFrame) -> int:
    losses = trades_df["pnl"] < 0
    if losses.sum() == 0:
        return 0
    groups = (losses != losses.shift()).cumsum()
    streaks = losses.groupby(groups).cumsum()
    return int(streaks.max())


def _approximate_period_returns(equity: pd.Series, *, window: int) -> pd.Series:
    """
    Approximate period returns by chunking the equity curve into fixed-size windows
    and computing geometric compounding per chunk.
    """
    if equity.empty or len(equity) < window + 1:
        return pd.Series(dtype=float)
    # Convert to returns per step
    step_returns = equity.pct_change().dropna()
    # Truncate to full windows
    length = (len(step_returns) // window) * window
    if length < window:
        return pd.Series(dtype=float)
    reshaped = step_returns.iloc[:length].to_numpy().reshape(-1, window)
    compounded = (1 + reshaped).prod(axis=1) - 1
    return pd.Series(compounded)

def _monte_carlo_ruin(
    return_pct: pd.Series,
    *,
    horizon: int = 250,
    ruin_threshold: float = -0.5,
    trials: int = 5000,
) -> float:
    if return_pct.empty:
        return 0.0
    returns = return_pct.dropna().values
    if len(returns) < 2:
        return 0.0
    mean = np.mean(returns)
    std = np.std(returns, ddof=1)
    if np.isclose(std, 0.0):
        return float(returns.mean() < ruin_threshold)
    rng = np.random.default_rng()
    shocks = rng.normal(mean, std, size=(trials, horizon))
    cumulative = np.cumsum(shocks, axis=1)
    ruin = (cumulative <= ruin_threshold * 100).any(axis=1)
    return float(ruin.mean())

