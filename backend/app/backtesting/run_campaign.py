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
from app.backtesting.tracking_error import TrackingErrorCalculator
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

    # Calculate tracking error summary for base scenario
    tracking_error_summary = None
    equity_theoretical = result.get("equity_theoretical", [])
    equity_realistic = result.get("equity_realistic", [])
    if equity_theoretical and equity_realistic and len(equity_theoretical) > 1 and len(equity_realistic) > 1:
        # Get timeframe from result metadata if available, default to daily (365 bars/year)
        timeframe = result.get("metadata", {}).get("timeframe", "1d")
        bars_per_year_map = {
            "15m": 365 * 24 * 4,
            "30m": 365 * 24 * 2,
            "1h": 365 * 24,
            "4h": 365 * 6,
            "1d": 365,
            "1w": 52,
        }
        bars_per_year = bars_per_year_map.get(timeframe, 365)
        
        tracking_error_calc = TrackingErrorCalculator.from_curves(
            theoretical=equity_theoretical,
            realistic=equity_realistic,
            bars_per_year=bars_per_year,
        )
        tracking_error_summary = tracking_error_calc.to_dict()

    scenarios: dict[str, Any] = {}
    for label, factor in SENSITIVITY_FACTORS.items():
        if label == "base":
            scenarios[label] = {
                "commission": commission_rate,
                "slippage": base_slippage,
                "metrics": metrics,
                "final_capital": result["final_capital"],
                "initial_capital": result["initial_capital"],
                "tracking_error_summary": tracking_error_summary,
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
        
        # Calculate tracking error for scenario
        scenario_tracking_error_summary = None
        scenario_equity_theoretical = scenario_result.get("equity_theoretical", [])
        scenario_equity_realistic = scenario_result.get("equity_realistic", [])
        if scenario_equity_theoretical and scenario_equity_realistic and len(scenario_equity_theoretical) > 1:
            timeframe = scenario_result.get("metadata", {}).get("timeframe", "1d")
            bars_per_year = bars_per_year_map.get(timeframe, 365)
            scenario_tracking_error_calc = TrackingErrorCalculator.from_curves(
                theoretical=scenario_equity_theoretical,
                realistic=scenario_equity_realistic,
                bars_per_year=bars_per_year,
            )
            scenario_tracking_error_summary = scenario_tracking_error_calc.to_dict()
        
        scenarios[label] = {
            "commission": scenario_engine.commission,
            "slippage": scenario_engine.slippage,
            "metrics": scenario_metrics,
            "final_capital": scenario_result["final_capital"],
            "initial_capital": scenario_result["initial_capital"],
            "tracking_error_summary": scenario_tracking_error_summary,
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
            "gap_events": result.get("gap_events", []),
            "integrity": _integrity_snapshot(result.get("trades", [])),
            "tracking_error_summary": tracking_error_summary,
        },
        "cost_scenarios": scenarios,
    }
    return payload


def _integrity_snapshot(trades: list[dict[str, Any]]) -> dict[str, float]:
    if not trades:
        return {}
    total = len(trades)
    partials = sum(1 for trade in trades if trade.get("fill_ratio") is not None and trade.get("fill_ratio", 1.0) < 0.999)
    entry_slippage = [float(trade.get("avg_entry_slippage_bps", 0.0)) for trade in trades if trade.get("avg_entry_slippage_bps") is not None]
    exit_slippage = [float(trade.get("exit_slippage_bps", 0.0)) for trade in trades if trade.get("exit_slippage_bps") is not None]
    return {
        "partial_fill_rate": partials / total if total else 0.0,
        "avg_entry_slippage_bps": sum(entry_slippage) / len(entry_slippage) if entry_slippage else 0.0,
        "avg_exit_slippage_bps": sum(exit_slippage) / len(exit_slippage) if exit_slippage else 0.0,
    }


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





