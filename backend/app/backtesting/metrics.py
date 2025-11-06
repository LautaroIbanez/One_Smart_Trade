"""Calculate professional backtesting metrics."""
from __future__ import annotations

from typing import Dict, Any, List
import pandas as pd
import numpy as np


def calculate_metrics(backtest_result: Dict[str, Any]) -> Dict[str, float]:
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

    return {
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
    }


def _calculate_rolling_metrics(trades_df: pd.DataFrame, equity_curve: List[float], window_days: int) -> Dict[str, Any]:
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

