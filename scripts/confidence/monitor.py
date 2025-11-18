"""Monitoreo continuo de calibración de confianza."""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import click
import numpy as np
import pandas as pd
import requests
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_PATH = REPO_ROOT / "backend"
if str(BACKEND_PATH) not in sys.path:
    sys.path.append(str(BACKEND_PATH))

from app.core.database import SessionLocal  # noqa: E402
from app.db.models import SignalOutcomeORM  # noqa: E402
from app.confidence.calibrator import expected_calibration_error, reliability_curve  # noqa: E402

DIAGNOSTICS_FILE = REPO_ROOT / "diagnostics.csv"


def _load_recent_signals(start: datetime, end: datetime) -> pd.DataFrame:
    with SessionLocal() as session:
        stmt = (
            session.query(SignalOutcomeORM)
            .filter(SignalOutcomeORM.decision_timestamp >= start)
            .filter(SignalOutcomeORM.decision_timestamp <= end)
        )
        rows = stmt.all()
    if not rows:
        return pd.DataFrame()
    records = []
    for row in rows:
        records.append(
            {
                "regime": (row.market_regime or "unknown").lower(),
                "confidence": float(row.confidence_raw or 0.0) / 100.0,
                "outcome": (row.outcome or "open").lower(),
                "pnl_pct": row.pnl_pct,
            }
        )
    df = pd.DataFrame.from_records(records)
    df["hit"] = np.where(
        (df["outcome"] == "win") | (df["pnl_pct"].fillna(0.0) >= 0.0),
        1,
        np.where(df["outcome"] == "loss", 0, np.nan),
    )
    df = df.dropna(subset=["hit"])
    return df


def _compute_metrics(df: pd.DataFrame) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    for regime, bucket in df.groupby("regime"):
        if bucket.empty:
            continue
        y_true = bucket["hit"].astype(int).to_numpy()
        y_prob = np.clip(bucket["confidence"].to_numpy(), 0.0, 1.0)
        brier = float(np.mean((y_prob - y_true) ** 2))
        ece = expected_calibration_error(y_true, y_prob)
        curve = reliability_curve(y_true, y_prob)
        metrics.append(
            {
                "regime": regime,
                "rows": int(len(bucket)),
                "brier": brier,
                "ece": ece,
                "reliability_curve": curve,
            }
        )
    return metrics


def _maybe_push_prometheus(metrics: list[dict[str, Any]], pushgateway: str | None) -> None:
    if not pushgateway:
        return
    registry = CollectorRegistry()
    g_brier = Gauge("confidence_calibration_brier", "Brier score (lower is better)", ["regime"], registry=registry)
    g_ece = Gauge("confidence_calibration_ece", "Expected Calibration Error", ["regime"], registry=registry)
    for m in metrics:
        g_brier.labels(regime=m["regime"]).set(m["brier"])
        g_ece.labels(regime=m["regime"]).set(m["ece"])
    push_to_gateway(pushgateway, job="confidence_monitor", registry=registry)


def _maybe_send_slack(webhook: str | None, payload: dict[str, Any]) -> None:
    if not webhook:
        return
    try:
        response = requests.post(webhook, json=payload, timeout=10)
        response.raise_for_status()
    except Exception:
        click.echo("Failed to send Slack alert", err=True)


def _append_diagnostics(row: dict[str, Any]) -> None:
    header = ["timestamp", "component", "regime", "brier", "ece", "rows", "status", "details"]
    file_exists = DIAGNOSTICS_FILE.exists()
    with DIAGNOSTICS_FILE.open("a", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=header)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


@click.command()
@click.option("--lookback-days", type=int, default=28, show_default=True, help="Ventana de análisis en días.")
@click.option("--min-rows", type=int, default=200, show_default=True, help="Mínimo de señales para considerar válido.")
@click.option("--max-brier", type=float, default=0.08, show_default=True, help="Umbral máximo de Brier score.")
@click.option("--max-ece", type=float, default=0.05, show_default=True, help="Umbral máximo de Expected Calibration Error.")
@click.option("--slack-webhook", envvar="SLACK_ALERT_WEBHOOK", help="Webhook de Slack para alertas.")
@click.option("--pushgateway", envvar="PROM_PUSHGATEWAY", help="URL de Prometheus Pushgateway.")
@click.option("--auto-retrain", is_flag=True, default=False, help="Disparar reentrenamiento automático si se detecta drift.")
def main(lookback_days: int, min_rows: int, max_brier: float, max_ece: float, slack_webhook: str | None, pushgateway: str | None, auto_retrain: bool) -> None:
    """Calcula métricas de calibración recientes y dispara alertas si exceden umbrales."""
    end = datetime.utcnow()
    start = end - timedelta(days=lookback_days)
    df = _load_recent_signals(start, end)
    if df.empty:
        click.echo("No hay señales suficientes en la ventana analizada.")
        return

    metrics = _compute_metrics(df)
    if not metrics:
        click.echo("Los datos disponibles no incluyen outcomes cerrados.")
        return

    status_summary: dict[str, str] = defaultdict(lambda: "healthy")
    alert_blocks = []
    for metric in metrics:
        regime = metric["regime"]
        rows = metric["rows"]
        status = "healthy"
        if rows < min_rows:
            status = "insufficient_data"
        elif metric["brier"] > max_brier or metric["ece"] > max_ece:
            status = "drift"
            alert_blocks.append(
                f"*{regime}* → Brier: {metric['brier']:.3f} / ECE: {metric['ece']:.3f} (n={rows})"
            )
        status_summary[regime] = status
        _append_diagnostics(
            {
                "timestamp": end.isoformat(),
                "component": "confidence_monitor",
                "regime": regime,
                "brier": f"{metric['brier']:.4f}",
                "ece": f"{metric['ece']:.4f}",
                "rows": rows,
                "status": status,
                "details": json.dumps(metric["reliability_curve"]),
            }
        )

    _maybe_push_prometheus(metrics, pushgateway)

    if alert_blocks:
        payload = {
            "text": ":warning: Drift detectado en calibración de confianza",
            "attachments": [
                {
                    "color": "#f97316",
                    "fields": [
                        {"title": "Resumen", "value": "\n".join(alert_blocks), "short": False},
                    ],
                    "footer": f"Ventana: {lookback_days}d, MinRows={min_rows}",
                }
            ],
        }
        _maybe_send_slack(slack_webhook, payload)
        click.echo("Drift detectado. Se enviaron alertas.")
        
        # Reentrenamiento automático si está habilitado
        if auto_retrain:
            _trigger_retraining(start, end)
    else:
        click.echo("Calibración dentro de umbrales.")


def _trigger_retraining(start: datetime, end: datetime) -> None:
    """Dispara reentrenamiento automático con dataset reciente."""
    import subprocess
    from pathlib import Path
    
    click.echo("Iniciando reentrenamiento automático...")
    
    # 1. Construir dataset reciente
    build_cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "confidence" / "build_dataset.py"),
        "--start-date", start.strftime("%Y-%m-%d"),
        "--end-date", end.strftime("%Y-%m-%d"),
    ]
    
    try:
        result = subprocess.run(build_cmd, capture_output=True, text=True, check=True, cwd=str(REPO_ROOT))
        # Extraer path del dataset del output
        output_lines = result.stdout.strip().split("\n")
        dataset_path = None
        for line in output_lines:
            if "Dataset generado:" in line:
                # Formato: "Dataset generado: artifacts/confidence/datasets/20241201T120000Z_abc12345 (1234 filas)"
                parts = line.split(": ", 1)
                if len(parts) > 1:
                    dataset_path_str = parts[1].split(" (")[0].strip()
                    dataset_path = REPO_ROOT / dataset_path_str
                    break
        
        if not dataset_path or not dataset_path.exists():
            click.echo("No se pudo determinar el path del dataset generado", err=True)
            return
        
        # 2. Entrenar calibradores
        train_cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "confidence" / "train_calibrators.py"),
            "--dataset-path", str(dataset_path),
            "--max-ece", "0.05",
            "--max-brier", "0.08",
        ]
        
        result = subprocess.run(train_cmd, capture_output=True, text=True, check=True, cwd=str(REPO_ROOT))
        click.echo("Reentrenamiento completado exitosamente.")
        click.echo(result.stdout)
        
    except subprocess.CalledProcessError as exc:
        click.echo(f"Error en reentrenamiento automático: {exc}", err=True)
        click.echo(f"stderr: {exc.stderr}", err=True)
    except Exception as exc:
        click.echo(f"Error inesperado en reentrenamiento: {exc}", err=True)


if __name__ == "__main__":
    main()

