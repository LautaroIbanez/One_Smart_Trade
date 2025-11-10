from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd

from app.core.database import SessionLocal
from app.db.models import BacktestResultORM

REPORT_PATH = Path("docs/backtest-report.md")
ASSETS_DIR = Path("docs/assets")


def _load_results() -> list[BacktestResultORM]:
    with SessionLocal() as db:
        return db.query(BacktestResultORM).order_by(BacktestResultORM.created_at.asc()).all()


def _plot_equity(curve: list[float], title: str, filename: Path) -> None:
    if not curve:
        return
    filename.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(10, 4))
    plt.plot(curve, color="#2563eb", linewidth=1.4)
    plt.title(title)
    plt.xlabel("Observaciones")
    plt.ylabel("Capital")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(filename, dpi=150)
    plt.close()


def _plot_scenarios(scenarios: dict[str, Any], title: str, filename: Path) -> None:
    data = []
    labels = []
    for label, payload in scenarios.items():
        metrics = payload.get("metrics", {})
        total_return = metrics.get("total_return", 0.0)
        data.append(total_return)
        labels.append(label.capitalize())
    if not data:
        return
    filename.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(6, 4))
    plt.bar(labels, data, color=["#16a34a", "#2563eb", "#dc2626"])
    plt.title(title)
    plt.ylabel("Retorno total (%)")
    plt.grid(axis="y", alpha=0.2)
    plt.tight_layout()
    plt.savefig(filename, dpi=150)
    plt.close()


def _format_metrics_row(name: str, metrics: dict[str, Any]) -> str:
    return (
        f"| {name} | {metrics.get('cagr', 0.0):.2f}% | {metrics.get('sharpe', 0.0):.2f} | "
        f"{metrics.get('sortino', 0.0):.2f} | {metrics.get('max_drawdown', 0.0):.2f}% | "
        f"{metrics.get('win_rate', 0.0):.2f}% | {metrics.get('profit_factor', 0.0):.2f} |"
    )


def build_campaign_report() -> None:
    results = _load_results()
    if not results:
        REPORT_PATH.write_text(
            "# One Smart Trade — Backtest\n\nNo existen resultados almacenados. Ejecuta `python -m app.backtesting.run_campaign` para generarlos.\n",
            encoding="utf-8",
        )
        return

    sections: list[str] = [
        "# One Smart Trade — Backtest Campaign",
        "Este informe resume las campañas caminantes ejecutadas y persistidas en la base de datos.",
    ]

    summary_rows = []
    for idx, result in enumerate(results, start=1):
        metrics = result.metrics or {}
        segment = metrics.get("segment", {})
        base_result = metrics.get("base_result", {})
        base_metrics = base_result.get("metrics", {})
        scenarios = metrics.get("cost_scenarios", {})

        equity_curve = base_result.get("equity_curve", [])
        equity_chart = ASSETS_DIR / f"campaign_equity_segment_{idx}.png"
        _plot_equity(
            equity_curve,
            title=f"Equity Curve Segment {idx}",
            filename=equity_chart,
        )

        scenario_chart = ASSETS_DIR / f"campaign_scenarios_segment_{idx}.png"
        _plot_scenarios(
            scenarios,
            title=f"Retorno total por escenario (Segmento {idx})",
            filename=scenario_chart,
        )

        sections.append(
            dedent(
                f"""
                ## Segmento {idx}: {segment.get("start", "N/A")} → {segment.get("end", "N/A")}
                - Versión: `{result.version}`
                - Ventana: {segment.get("window_days", 0)} días
                - Comisión base: {base_result.get("commission", 0.0):.4f}
                - Deslizamiento base: {base_result.get("slippage", 0.0):.4f}

                ![Equity Segmento {idx}](assets/{equity_chart.name})

                | Escenario | CAGR | Sharpe | Sortino | Max DD | Win Rate | Profit Factor |
                | --- | --- | --- | --- | --- | --- | --- |
                {_format_metrics_row("Base", base_metrics)}
                {_format_metrics_row("Optimista", scenarios.get("optimistic", {}).get("metrics", {}))}
                {_format_metrics_row("Estresado", scenarios.get("stressed", {}).get("metrics", {}))}

                ![Sensibilidad Segmento {idx}](assets/{scenario_chart.name})
                """
            ).strip()
        )

        summary_rows.append(
            {
                "segment": idx,
                "start": segment.get("start"),
                "end": segment.get("end"),
                "cagr": base_metrics.get("cagr", 0.0),
                "sharpe": base_metrics.get("sharpe", 0.0),
                "max_drawdown": base_metrics.get("max_drawdown", 0.0),
            }
        )

    df = pd.DataFrame(summary_rows)
    if not df.empty:
        sections.insert(
            2,
            dedent(
                f"""
                ## Resumen Ejecutivo

                | Segmento | Inicio | Fin | CAGR (%) | Sharpe | Max DD (%) |
                | --- | --- | --- | --- | --- | --- |
                {_render_summary_table(df)}
                """
            ).strip(),
        )

    REPORT_PATH.write_text("\n\n".join(sections) + "\n", encoding="utf-8")


def _render_summary_table(df: pd.DataFrame) -> str:
    rows = []
    for _, row in df.iterrows():
        rows.append(
            f"| {int(row['segment'])} | {row['start']} | {row['end']} | {row['cagr']:.2f} | {row['sharpe']:.2f} | {row['max_drawdown']:.2f} |"
        )
    return "\n".join(rows)


__all__ = ["build_campaign_report"]