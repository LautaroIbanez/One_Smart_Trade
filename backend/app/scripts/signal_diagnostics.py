from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.logging import setup_logging
from app.data.curation import DataCuration
from app.quant.signal_engine import generate_signal
from app.quant.strategies import PARAMS as STRATEGY_PARAMS


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze aggregate signal distributions over historical curated data."
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=180,
        help="Number of days of historical data to analyze (default: 180)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to export the diagnostics as CSV",
    )
    parser.add_argument(
        "--band",
        type=float,
        default=0.15,
        help="Neutral band width to evaluate aggregate_score clustering (default: 0.15)",
    )
    return parser


def _load_curated(curation: DataCuration, interval: str, days: int) -> pd.DataFrame:
    df = curation.get_historical_curated(interval, days=days)
    if df.empty:
        raise ValueError(f"No curated data available for interval {interval}")
    return df.sort_values("open_time").reset_index(drop=True)


def _slice_up_to(df: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    return df[df["open_time"] <= cutoff].copy()


def run_diagnostics(lookback_days: int, band: float) -> dict[str, Any]:
    setup_logging()
    curation = DataCuration()
    df_daily = _load_curated(curation, "1d", days=lookback_days + 30)
    df_hourly = _load_curated(curation, "1h", days=lookback_days + 30)

    aggregate_params = STRATEGY_PARAMS.get("aggregate", {})
    rr_floor = float(aggregate_params.get("risk_reward_floor", 1.2))

    records: list[dict[str, Any]] = []
    reason_counter: Counter[str] = Counter()

    warmup = 120
    for idx in range(warmup, len(df_daily)):
        ts = pd.Timestamp(df_daily["open_time"].iloc[idx])
        df_1d_slice = _slice_up_to(df_daily, ts)
        df_1h_slice = _slice_up_to(df_hourly, ts)
        if df_1h_slice.empty or df_1d_slice.empty:
            continue
        try:
            signal = generate_signal(df_1h_slice, df_1d_slice, mc_trials=0)
        except ValueError:
            continue

        breakdown = signal.get("signal_breakdown", {})
        risk_metrics = signal.get("risk_metrics", {})
        rr_ratio = float(risk_metrics.get("risk_reward_ratio", 0.0) or 0.0)
        rr_rejected = risk_metrics.get("rejected_reason") == "risk_reward_floor"

        raw_score = float(breakdown.get("raw_aggregate_score", breakdown.get("aggregate_score", 0.0)) or 0.0)
        record = {
            "date": datetime.fromisoformat(str(ts)).date().isoformat(),
            "signal": signal.get("signal"),
            "aggregate_score": float(breakdown.get("aggregate_score", 0.0) or 0.0),
            "raw_aggregate_score": raw_score,
            "confidence": float(signal.get("confidence", 0.0)),
            "risk_reward_ratio": rr_ratio,
            "rr_rejected": bool(rr_rejected),
            "tp_probability": float(risk_metrics.get("tp_probability", 0.0) or 0.0),
            "sl_probability": float(risk_metrics.get("sl_probability", 0.0) or 0.0),
        }
        votes = signal.get("votes", {})
        for key in ("BUY", "SELL", "HOLD"):
            record[f"votes_{key.lower()}"] = int(votes.get(key, 0))

        if signal.get("signal") == "HOLD":
            for strat in signal.get("signals", []):
                reason = strat.get("reason") or "unknown"
                reason_counter[f"{strat.get('signal')}-{reason}"] += 1
        records.append(record)

    if not records:
        raise RuntimeError("Insufficient data to produce diagnostics. Ensure curated datasets exist.")

    df = pd.DataFrame(records)
    hold_mask = df["signal"] == "HOLD"
    directional_mask = df["signal"].isin(["BUY", "SELL"])
    neutral_mask = df["raw_aggregate_score"].between(-band, band)

    summary = {
        "total_observations": int(len(df)),
        "holds": int(hold_mask.sum()),
        "holds_pct": round(float(hold_mask.mean() * 100.0), 2),
        "directional": int(directional_mask.sum()),
        "directional_pct": round(float(directional_mask.mean() * 100.0), 2),
        "neutral_band_pct": round(float(neutral_mask.mean() * 100.0), 2),
        "rr_below_floor_pct": round(float((df["risk_reward_ratio"] < rr_floor).mean() * 100.0), 2),
        "rr_rejected_pct": round(float(df["rr_rejected"].mean() * 100.0), 2),
        "aggregate_score_mean": round(float(df["aggregate_score"].mean()), 4),
        "aggregate_score_median": round(float(df["aggregate_score"].median()), 4),
        "aggregate_score_std": round(float(df["aggregate_score"].std()), 4),
        "aggregate_score_p5": round(float(df["aggregate_score"].quantile(0.05)), 4),
        "aggregate_score_p95": round(float(df["aggregate_score"].quantile(0.95)), 4),
        "raw_score_mean": round(float(df["raw_aggregate_score"].mean()), 4),
        "raw_score_median": round(float(df["raw_aggregate_score"].median()), 4),
        "confidence_mean": round(float(df["confidence"].mean()), 2),
        "rr_floor": rr_floor,
        "top_hold_reasons": reason_counter.most_common(5),
        "records": df,
    }
    return summary


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        summary = run_diagnostics(args.lookback_days, args.band)
    except Exception as exc:  # noqa: BLE001
        print(f"✗ Diagnostics failed: {exc}")
        raise SystemExit(1) from exc

    df: pd.DataFrame = summary.pop("records")

    print("=== Signal Diagnostics Summary ===")
    for key, value in summary.items():
        if key == "top_hold_reasons":
            print(f"{key}:")
            for reason, count in value:
                print(f"  - {reason}: {count}")
        else:
            print(f"{key}: {value}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(args.output, index=False)
        print(f"Diagnostics exported to {args.output}")


if __name__ == "__main__":
    main()

