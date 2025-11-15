from __future__ import annotations

import argparse
from datetime import datetime

import pandas as pd
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.db.models import PerformancePeriodicORM, PeriodicHorizon
from app.analytics.periodic_metrics import PeriodicMetricsBuilder


def load_equity_from_csv(path: str, value_column: str = "equity") -> pd.Series:
    df = pd.read_csv(path)
    # Try common column names for timestamp
    ts_col = next((c for c in ["timestamp", "date", "time"] if c in df.columns), None)
    if ts_col:
        idx = pd.to_datetime(df[ts_col])
    else:
        # Fallback to range index with daily frequency
        idx = pd.date_range(end=datetime.utcnow().date(), periods=len(df), freq="D")
    values = df[value_column] if value_column in df.columns else df.iloc[:, -1]
    return pd.Series(values.values, index=idx).astype(float)


def persist_periodic(db: Session, run_id: str, pm_list) -> int:
    rows = 0
    for pm in pm_list:
        series = pm.distribution
        if pm.horizon == "monthly":
            labels = [d.strftime("%Y-%m") for d in series.index]
            horizon = PeriodicHorizon.monthly
        else:
            labels = [f"{d.year}-Q{((d.month-1)//3)+1}" for d in series.index]
            horizon = PeriodicHorizon.quarterly
        for label, value in zip(labels, series.values):
            rec = PerformancePeriodicORM(
                run_id=run_id,
                period=label,
                horizon=horizon,
                mean=float(value),
                std=0.0,
                p25=0.0,
                p75=0.0,
                skew=0.0,
                kurtosis=0.0,
                negative_flag=bool(value < 0),
            )
            db.add(rec)
            rows += 1
    db.commit()
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate periodic metrics from equity CSV and persist")
    parser.add_argument("--run-id", required=True, help="Identifier of the backtest run (e.g., params digest)")
    parser.add_argument("--csv", required=True, help="Path to CSV containing equity curve")
    parser.add_argument("--value-column", default="equity", help="Column name for equity values (default: equity)")
    args = parser.parse_args()

    equity = load_equity_from_csv(args.csv, value_column=args.value_column)
    builder = PeriodicMetricsBuilder()
    validation = builder.validate_inputs(equity, max_gap_days=5, min_months=12)
    if not validation.get("ok", False):
        print(f"WARNING: equity validation failed reason={validation.get('reason')} coverage={validation.get('coverage_pct')} max_gap_days={validation.get('max_gap_days')} months={validation.get('months')}")
    else:
        print(f"Validation ok: coverage={validation.get('coverage_pct')} max_gap_days={validation.get('max_gap_days')} months={validation.get('months')}")
    metrics = builder.build(equity)

    with SessionLocal() as db:
        rows = persist_periodic(db, args.run_id, metrics)
        print(f"Inserted {rows} periodic rows for run_id={args.run_id}")


if __name__ == "__main__":
    main()


