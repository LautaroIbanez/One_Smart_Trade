"""Generate backtest report with charts and markdown export."""
from __future__ import annotations

from typing import Dict, Any
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from app.backtesting.metrics import calculate_metrics


def generate_report(backtest_result: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
    """Generate backtest report with charts and markdown."""
    metrics = calculate_metrics(backtest_result)
    trades = backtest_result.get("trades", [])
    equity_curve = backtest_result.get("equity_curve", [])

    output_dir.mkdir(parents=True, exist_ok=True)

    # Equity curve chart
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(equity_curve, label="Equity", color="#3b82f6")
    ax.axhline(y=backtest_result["initial_capital"], color="gray", linestyle="--", label="Initial Capital")
    ax.set_xlabel("Trade #")
    ax.set_ylabel("Capital ($)")
    ax.set_title("Equity Curve")
    ax.legend()
    ax.grid(True, alpha=0.3)
    equity_path = output_dir / "equity_curve.png"
    plt.savefig(equity_path, dpi=150, bbox_inches="tight")
    plt.close()

    # Drawdown chart
    equity_series = pd.Series(equity_curve)
    running_max = equity_series.expanding().max()
    drawdown = ((equity_series - running_max) / running_max) * 100

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.fill_between(range(len(drawdown)), drawdown, 0, color="#ef4444", alpha=0.3)
    ax.plot(drawdown, color="#ef4444", label="Drawdown %")
    ax.set_xlabel("Trade #")
    ax.set_ylabel("Drawdown (%)")
    ax.set_title("Drawdown Chart")
    ax.legend()
    ax.grid(True, alpha=0.3)
    dd_path = output_dir / "drawdown.png"
    plt.savefig(dd_path, dpi=150, bbox_inches="tight")
    plt.close()

    # Generate markdown report
    md_content = f"""# Backtest Report - One Smart Trade

## Summary

- **Period:** {backtest_result['start_date']} to {backtest_result['end_date']}
- **Initial Capital:** ${backtest_result['initial_capital']:,.2f}
- **Final Capital:** ${backtest_result['final_capital']:,.2f}
- **Total Return:** {metrics['total_return']:.2f}%

## Performance Metrics

| Metric | Value |
|--------|-------|
| CAGR | {metrics['cagr']:.2f}% |
| Sharpe Ratio | {metrics['sharpe']:.2f} |
| Sortino Ratio | {metrics['sortino']:.2f} |
| Max Drawdown | {metrics['max_drawdown']:.2f}% |
| Win Rate | {metrics['win_rate']:.2f}% |
| Profit Factor | {metrics['profit_factor']:.2f} |
| Expectancy | ${metrics['expectancy']:.2f} |
| Calmar Ratio | {metrics['calmar']:.2f} |

## Trade Statistics

- **Total Trades:** {metrics['total_trades']}
- **Winning Trades:** {metrics['winning_trades']}
- **Losing Trades:** {metrics['losing_trades']}

## Charts

### Equity Curve

![Equity Curve](equity_curve.png)

### Drawdown

![Drawdown](drawdown.png)

## Disclaimer

This backtest is for educational purposes only. Past performance does not guarantee future results. Trading cryptocurrencies involves significant risk.
"""

    report_path = output_dir / "backtest-report.md"
    report_path.write_text(md_content, encoding="utf-8")

    return {
        "metrics": metrics,
        "report_path": str(report_path),
        "equity_chart": str(equity_path),
        "drawdown_chart": str(dd_path),
    }

