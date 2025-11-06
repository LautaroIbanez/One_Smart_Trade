"""Generate backtest report with charts and markdown export."""
from __future__ import annotations

from typing import Dict, Any
from pathlib import Path
from datetime import datetime
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from app.backtesting.metrics import calculate_metrics
from app.core.logging import logger


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

    # Returns distribution
    if trades:
        df_trades = pd.DataFrame(trades)
        returns = df_trades["return_pct"].values

        fig, ax = plt.subplots(figsize=(10, 6))
        ax.hist(returns, bins=30, color="#3b82f6", alpha=0.7, edgecolor="black")
        ax.axvline(np.mean(returns), color="#ef4444", linestyle="--", label=f"Mean: {np.mean(returns):.2f}%")
        ax.set_xlabel("Return (%)")
        ax.set_ylabel("Frequency")
        ax.set_title("Returns Distribution")
        ax.legend()
        ax.grid(True, alpha=0.3)
        dist_path = output_dir / "returns_distribution.png"
        plt.savefig(dist_path, dpi=150, bbox_inches="tight")
        plt.close()
    else:
        dist_path = None

    # Buy & Hold comparison - use actual first and last prices from the period
    buy_hold_return = 0.0
    buy_hold_cagr = 0.0
    first_price = backtest_result.get("first_price", 0.0)
    last_price = backtest_result.get("last_price", 0.0)
    
    if first_price > 0 and last_price > 0:
        buy_hold_return = ((last_price - first_price) / first_price) * 100
        
        # Calculate Buy & Hold CAGR
        start_dt = pd.to_datetime(backtest_result["start_date"])
        end_dt = pd.to_datetime(backtest_result["end_date"])
        days = (end_dt - start_dt).days
        years = days / 365.25
        if years > 0:
            buy_hold_cagr = ((last_price / first_price) ** (1 / years) - 1) * 100

        strategy_return = metrics.get("total_return", 0.0)

        fig, ax = plt.subplots(figsize=(10, 6))
        bars = ax.bar(["Strategy", "Buy & Hold"], [strategy_return, buy_hold_return], color=["#3b82f6", "#10b981"])
        ax.set_ylabel("Total Return (%)")
        ax.set_title("Strategy vs Buy & Hold")
        ax.grid(True, alpha=0.3, axis="y")
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height, f'{height:.1f}%', ha='center', va='bottom')
        bh_path = output_dir / "buy_hold_comparison.png"
        plt.savefig(bh_path, dpi=150, bbox_inches="tight")
        plt.close()
    else:
        bh_path = None

    # Monthly returns chart
    monthly_returns = None
    if trades:
        df_trades = pd.DataFrame(trades)
        df_trades["exit_time"] = pd.to_datetime(df_trades["exit_time"])
        df_trades["month"] = df_trades["exit_time"].dt.to_period("M")
        monthly_returns = df_trades.groupby("month")["return_pct"].sum()
        
        fig, ax = plt.subplots(figsize=(12, 6))
        colors = ["#10b981" if x >= 0 else "#ef4444" for x in monthly_returns.values]
        ax.bar(range(len(monthly_returns)), monthly_returns.values, color=colors, alpha=0.7)
        ax.axhline(y=0, color="black", linestyle="-", linewidth=0.5)
        ax.set_xlabel("Month")
        ax.set_ylabel("Return (%)")
        ax.set_title("Monthly Returns")
        ax.set_xticks(range(len(monthly_returns)))
        ax.set_xticklabels([str(p) for p in monthly_returns.index], rotation=45, ha="right")
        ax.grid(True, alpha=0.3, axis="y")
        monthly_path = output_dir / "monthly_returns.png"
        plt.savefig(monthly_path, dpi=150, bbox_inches="tight")
        plt.close()
    else:
        monthly_path = None

    # Calculate duration
    start_dt = pd.to_datetime(backtest_result["start_date"])
    end_dt = pd.to_datetime(backtest_result["end_date"])
    duration_days = (end_dt - start_dt).days
    duration_years = duration_days / 365.25

    # Prepare trade statistics for markdown
    avg_win = 0.0
    avg_loss = 0.0
    largest_win = 0.0
    largest_loss = 0.0
    if trades:
        df_trades_md = pd.DataFrame(trades)
        if not df_trades_md.empty:
            winning = df_trades_md[df_trades_md['pnl'] > 0]
            losing = df_trades_md[df_trades_md['pnl'] < 0]
            avg_win = float(winning['pnl'].mean()) if len(winning) > 0 else 0.0
            avg_loss = float(losing['pnl'].mean()) if len(losing) > 0 else 0.0
            largest_win = float(df_trades_md['pnl'].max()) if not df_trades_md.empty else 0.0
            largest_loss = float(df_trades_md['pnl'].min()) if not df_trades_md.empty else 0.0

    # Generate comprehensive markdown report
    md_content = f"""# Backtest Report - One Smart Trade

> **Nota:** Este reporte es generado automáticamente por el motor de backtesting. Los resultados se actualizan periódicamente.
> **Generado:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

## Resumen Ejecutivo

Este reporte presenta los resultados del backtesting del sistema One Smart Trade sobre datos históricos de BTC/USDT. El backtesting incluye modelado de comisiones (0.1%) y slippage (0.05%) para simular condiciones realistas de ejecución.

## Período de Backtesting

- **Fecha Inicio:** {backtest_result['start_date']}
- **Fecha Fin:** {backtest_result['end_date']}
- **Duración:** {duration_days} días ({duration_years:.2f} años)
- **Capital Inicial:** ${backtest_result['initial_capital']:,.2f}
- **Capital Final:** ${backtest_result['final_capital']:,.2f}
- **Retorno Total:** {metrics['total_return']:.2f}%

## Métricas de Performance

### Métricas Principales

| Métrica | Valor | Benchmark (Buy & Hold) |
|---------|-------|------------------------|
| CAGR | {metrics['cagr']:.2f}% | {buy_hold_cagr:.2f}% |
| Sharpe Ratio | {metrics['sharpe']:.2f} | N/A |
| Sortino Ratio | {metrics['sortino']:.2f} | N/A |
| Max Drawdown | {metrics['max_drawdown']:.2f}% | N/A |
| Win Rate | {metrics['win_rate']:.2f}% | N/A |
| Profit Factor | {metrics['profit_factor']:.2f} | N/A |
| Expectancy | ${metrics['expectancy']:.2f} | N/A |
| Calmar Ratio | {metrics['calmar']:.2f} | N/A |

### Análisis Detallado

**Retorno y Rendimiento:**
- El sistema generó un retorno total de {metrics['total_return']:.2f}% durante el período de backtesting.
- La tasa de crecimiento anual compuesta (CAGR) fue de {metrics['cagr']:.2f}%, {'superior' if metrics['cagr'] > buy_hold_cagr else 'inferior'} al buy & hold ({buy_hold_cagr:.2f}%).

**Riesgo:**
- El drawdown máximo fue de {metrics['max_drawdown']:.2f}%, indicando el mayor retroceso desde un pico de capital.
- El ratio de Sharpe de {metrics['sharpe']:.2f} {'indica un buen ajuste riesgo-retorno' if metrics['sharpe'] > 1.0 else 'sugiere que el retorno ajustado por riesgo podría mejorarse'}.
- El ratio de Sortino de {metrics['sortino']:.2f} considera solo la volatilidad a la baja, siendo {'favorable' if metrics['sortino'] > 1.0 else 'moderado'}.

**Eficiencia Operativa:**
- Se ejecutaron {metrics['total_trades']} trades en total.
- La tasa de aciertos (Win Rate) fue de {metrics['win_rate']:.2f}%, con {metrics['winning_trades']} trades ganadores y {metrics['losing_trades']} perdedores.
- El Profit Factor de {metrics['profit_factor']:.2f} {'indica que las ganancias superan las pérdidas' if metrics['profit_factor'] > 1.0 else 'sugiere que las pérdidas superan las ganancias'}.
- La expectativa por trade es de ${metrics['expectancy']:.2f}.

## Trade Statistics

- **Total Trades:** {metrics['total_trades']}
- **Winning Trades:** {metrics['winning_trades']}
- **Losing Trades:** {metrics['losing_trades']}
- **Average Win:** ${avg_win:.2f}
- **Average Loss:** ${avg_loss:.2f}
- **Largest Win:** ${largest_win:.2f}
- **Largest Loss:** ${largest_loss:.2f}

## Gráficos

### Equity Curve

![Equity Curve](equity_curve.png)

La curva de equity muestra la evolución del capital a lo largo del tiempo. La línea punteada representa el capital inicial.

### Drawdown Chart

![Drawdown](drawdown.png)

El gráfico de drawdown muestra los períodos de retroceso desde máximos históricos. Valores negativos indican pérdidas desde el pico de capital.

### Returns Distribution

![Returns Distribution](returns_distribution.png)

La distribución de retornos muestra la frecuencia de diferentes niveles de retorno por trade. La línea vertical punteada indica la media.

{f'### Monthly Returns\n\n![Monthly Returns](monthly_returns.png)\n\nEl gráfico de retornos mensuales muestra la performance mes a mes. Barras verdes indican meses positivos, rojas indican meses negativos.\n\n' if monthly_path else ''}### Strategy vs Buy & Hold

![Buy & Hold Comparison](buy_hold_comparison.png)

Comparación directa entre el retorno de la estrategia y el buy & hold durante el mismo período.

## Comparativa vs Buy & Hold

- **Strategy Return:** {metrics['total_return']:.2f}%
- **Buy & Hold Return:** {buy_hold_return:.2f}%
- **Outperformance:** {metrics['total_return'] - buy_hold_return:.2f}%
- **Strategy CAGR:** {metrics['cagr']:.2f}%
- **Buy & Hold CAGR:** {buy_hold_cagr:.2f}%

{'La estrategia superó al buy & hold en ' + f'{metrics["total_return"] - buy_hold_return:.2f}%' if metrics['total_return'] > buy_hold_return else 'El buy & hold superó a la estrategia en ' + f'{buy_hold_return - metrics["total_return"]:.2f}%'} durante el período analizado.

## Análisis por Estrategia

El sistema utiliza múltiples estrategias combinadas (momentum, mean-reversion, breakout, volatilidad) con un mecanismo de votación para generar señales consolidadas. Los resultados mostrados reflejan la performance del sistema completo.

## Conclusiones

{'Los resultados del backtesting muestran una performance ' + ('positiva' if metrics['total_return'] > 0 else 'negativa') + ' durante el período analizado.'}
{'El sistema generó retornos consistentes con un drawdown máximo controlado.' if metrics['max_drawdown'] < 30 else 'El drawdown máximo sugiere períodos de alta volatilidad que requieren gestión de riesgo adecuada.'}
{'La tasa de aciertos y el profit factor indican una estrategia viable.' if metrics['win_rate'] > 50 and metrics['profit_factor'] > 1.0 else 'Se recomienda revisar los parámetros de entrada y salida para mejorar la tasa de aciertos.'}

**Limitaciones del Backtesting:**
- Los resultados históricos no garantizan performance futura.
- El modelado de slippage y comisiones es una aproximación.
- No se consideran condiciones de mercado extremas o eventos de cola.
- La ejecución real puede diferir debido a latencia y liquidez.

## Disclaimer

Este backtest es solo para fines educativos. El rendimiento pasado no garantiza resultados futuros. El trading de criptomonedas implica riesgos significativos. Este sistema no constituye asesoramiento financiero. Opere bajo su propio criterio y riesgo.
"""

    # Write to both output_dir and docs/backtest-report.md
    report_path = output_dir / "backtest-report.md"
    report_path.write_text(md_content, encoding="utf-8")
    logger.info(f"Backtest report written to {report_path}")
    
    # Also write to docs/backtest-report.md (project root)
    # Find project root by going up from backend/app/backtesting/report.py
    current_file = Path(__file__).resolve()
    # Go up: backend/app/backtesting -> backend/app -> backend -> project root
    project_root = current_file.parent.parent.parent.parent
    docs_path = project_root / "docs" / "backtest-report.md"
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    docs_path.write_text(md_content, encoding="utf-8")
    logger.info(f"Backtest report also written to {docs_path}")

    return {
        "metrics": metrics,
        "report_path": str(report_path),
        "equity_chart": str(equity_path),
        "drawdown_chart": str(dd_path),
    }

