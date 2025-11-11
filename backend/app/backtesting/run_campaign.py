"""Run walk-forward backtesting campaigns with versioned persistence."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.backtesting.engine import BacktestEngine
from app.backtesting.metrics import calculate_metrics
from app.core.database import SessionLocal
from app.core.logging import logger
from app.data.storage import CURATED_ROOT
from app.db.crud import save_backtest_result
from app.quant.strategies import PARAMS_PATH


DEFAULT_WINDOW_DAYS = 180
SENSITIVITY_FACTORS = {
    "optimistic": 0.5,
    "base": 1.0,
    "stressed": 1.5,
}


def _parse_date(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.strptime(value, "%Y-%m-%d")


def _hash_file(path: Path) -> str:
    if not path.exists():
        logger.warning(f"Cannot hash missing file: {path}")
        return "missing"
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _campaign_version(params_hash: str, dataset_hash: str, segment_start: datetime, segment_end: datetime) -> str:
    params_id = params_hash[:8] if params_hash != "missing" else "params000"
    data_id = dataset_hash[:8] if dataset_hash != "missing" else "data0000"
    return f"{params_id}-{data_id}-{segment_start:%Y%m%d}-{segment_end:%Y%m%d}"


def _run_segment(
    start: datetime,
    end: datetime,
    commission_rate: float,
    base_slippage: float,
) -> dict[str, Any]:
    engine = BacktestEngine(commission=commission_rate, slippage=base_slippage)
    result = engine.run_backtest(start, end)
    if "error" in result:
        raise RuntimeError(result.get("details", result["error"]))
    metrics = calculate_metrics(result)

    scenarios: dict[str, Any] = {}
    for label, factor in SENSITIVITY_FACTORS.items():
        if label == "base":
            scenarios[label] = {
                "commission": commission_rate,
                "slippage": base_slippage,
                "metrics": metrics,
                "final_capital": result["final_capital"],
                "initial_capital": result["initial_capital"],
            }
            continue

        scenario_engine = BacktestEngine(
            commission=commission_rate * factor,
            slippage=base_slippage * factor,
        )
        scenario_result = scenario_engine.run_backtest(start, end)
        if "error" in scenario_result:
            raise RuntimeError(scenario_result.get("details", scenario_result["error"]))
        scenario_metrics = calculate_metrics(scenario_result)
        scenarios[label] = {
            "commission": scenario_engine.commission,
            "slippage": scenario_engine.slippage,
            "metrics": scenario_metrics,
            "final_capital": scenario_result["final_capital"],
            "initial_capital": scenario_result["initial_capital"],
        }

    payload = {
        "segment": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "window_days": (end - start).days + 1,
        },
        "base_result": {
            "commission": commission_rate,
            "slippage": base_slippage,
            "final_capital": result["final_capital"],
            "initial_capital": result["initial_capital"],
            "trades": result.get("trades", []),
            "equity_curve": result.get("equity_curve", []),
            "metrics": metrics,
        },
        "cost_scenarios": scenarios,
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run walk-forward backtest campaign")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--walk-forward-window",
        type=int,
        default=DEFAULT_WINDOW_DAYS,
        help="Window size in days for each walk-forward segment (default: 180)",
    )
    parser.add_argument(
        "--cost-bps",
        type=float,
        default=10.0,
        help="Commission per trade in basis points (default: 10 bps)",
    )

    args = parser.parse_args()

    start_date = _parse_date(args.start)
    end_date = _parse_date(args.end)
    if start_date is None or end_date is None:
        raise ValueError("Start and end dates must be provided in YYYY-MM-DD format.")
    if start_date >= end_date:
        raise ValueError("Start date must be earlier than end date.")

    window_days = max(30, args.walk_forward_window)
    commission_rate = args.cost_bps / 10_000.0
    base_slippage = BacktestEngine.SLIPPAGE_RATE

    params_hash = _hash_file(PARAMS_PATH)
    curated_path = CURATED_ROOT / "1d" / "latest.parquet"
    dataset_hash = _hash_file(curated_path)

    logger.info(
        "Starting backtest campaign",
        extra={
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "window_days": window_days,
            "commission": commission_rate,
            "params_hash": params_hash[:8],
            "dataset_hash": dataset_hash[:8],
        },
    )

    segments = []
    current_start = start_date
    while current_start <= end_date:
        current_end = min(current_start + timedelta(days=window_days - 1), end_date)
        logger.info(f"Running segment {current_start.date()} → {current_end.date()}")
        segment_payload = _run_segment(current_start, current_end, commission_rate, base_slippage)
        segment_payload["metadata"] = {
            "params_hash": params_hash,
            "dataset_hash": dataset_hash,
            "cost_bps": args.cost_bps,
        }
        segments.append(segment_payload)

        version = _campaign_version(params_hash, dataset_hash, current_start, current_end)
        with SessionLocal() as db:
            metrics_payload = json.loads(json.dumps(segment_payload))
            save_backtest_result(
                db=db,
                version=version,
                start_date=segment_payload["segment"]["start"],
                end_date=segment_payload["segment"]["end"],
                metrics=metrics_payload,
            )

        current_start = current_end + timedelta(days=1)

    logger.info(f"Campaign completed with {len(segments)} segments persisted.")


if __name__ == "__main__":
    main()



