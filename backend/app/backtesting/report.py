from pathlib import Path
from textwrap import dedent

from .schemas import BacktestSummary

REPORT_PATH = Path("docs/backtest-report.md")


def write_report(summary: BacktestSummary) -> None:
    REPORT_PATH.write_text(
        dedent(
            f"""
            # One Smart Trade — Backtest

            ## Período analizado
            - Inicio: {summary.start_date:%Y-%m-%d}
            - Fin: {summary.end_date:%Y-%m-%d}
            - Días operados: {summary.trading_days}

            ## Métricas
            | Métrica | Estrategia | Buy & Hold |
            | --- | --- | --- |
            | CAGR | {summary.cagr:.2%} | {summary.bh_cagr:.2%} |
            | Sharpe | {summary.sharpe:.2f} | {summary.bh_sharpe:.2f} |
            | Sortino | {summary.sortino:.2f} | {summary.bh_sortino:.2f} |
            | Profit Factor | {summary.profit_factor:.2f} | — |
            | Max Drawdown | {summary.max_drawdown:.2%} | {summary.bh_max_drawdown:.2%} |

            ## Rolling KPIs
            Inserta las gráficas generadas automáticamente (equity, drawdown, win rate).

            ## Limitaciones
            - Slippage asumido: {summary.slippage_bps} bps.
            - Datos faltantes se rellenaron con forward-fill limitado a 3 velas.
            - No se simularon eventos macro extraordinarios (halvings, shocks de liquidez).
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

