"""Run sensitivity analysis with ±20% parameter variations for champion validation."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from app.backtesting.sensitivity import SensitivityRunner
from app.core.logging import logger


def generate_20pct_variations(base_params: dict[str, Any], critical_params: list[str]) -> dict[str, list[Any]]:
    """
    Generate ±20% variations for critical parameters.
    
    Args:
        base_params: Base parameters dictionary (nested structure)
        critical_params: List of parameter paths (e.g., "breakout.lookback")
        
    Returns:
        Parameter grid with variations
    """
    param_grid = {}
    
    for param_path in critical_params:
        # Navigate nested structure
        parts = param_path.split(".")
        current = base_params
        try:
            for part in parts[:-1]:
                current = current[part]
            base_value = current[parts[-1]]
        except (KeyError, TypeError):
            logger.warning(f"Parameter not found: {param_path}, skipping")
            continue
        
        # Generate ±20% variations
        if isinstance(base_value, (int, float)):
            variations = [
                base_value * 0.8,   # -20%
                base_value * 0.9,   # -10%
                base_value,         # base
                base_value * 1.1,   # +10%
                base_value * 1.2,   # +20%
            ]
            # Round appropriately
            if isinstance(base_value, int):
                variations = [int(round(v)) for v in variations]
            else:
                variations = [round(v, 4) for v in variations]
            param_grid[param_path] = variations
        else:
            logger.warning(f"Parameter {param_path} is not numeric, skipping")
    
    return param_grid


def get_critical_params() -> list[str]:
    """Get list of critical hyperparameters to test."""
    return [
        "breakout.lookback",
        "volatility.low_threshold",
        "volatility.high_threshold",
        "aggregate.vector_bias.momentum_bias_weight",
        "aggregate.vector_bias.breakout_slope_weight",
        "aggregate.buy_threshold",
        "aggregate.sell_threshold",
        "aggregate.vector_bias.momentum_alignment",
        "aggregate.multi_timeframe.ema21_slope_weight",
        "aggregate.multi_timeframe.intraday_momentum_weight",
    ]


def load_base_params(params_path: Path | None = None) -> dict[str, Any]:
    """Load base parameters from YAML file."""
    if params_path is None:
        # Try multiple possible paths
        possible_paths = [
            Path("backend/app/quant/params.yaml"),
            Path("app/quant/params.yaml"),
            Path(__file__).parent.parent.parent / "backend" / "app" / "quant" / "params.yaml",
        ]
        for path in possible_paths:
            if path.exists():
                params_path = path
                break
        
        if params_path is None or not params_path.exists():
            raise FileNotFoundError("Could not find params.yaml file")
    
    with params_path.open() as f:
        return yaml.safe_load(f) or {}


def generate_campaign_id(base_params: dict[str, Any], start_date: str, end_date: str) -> str:
    """Generate a deterministic campaign ID."""
    content = json.dumps({
        "params": base_params,
        "start_date": start_date,
        "end_date": end_date,
    }, sort_keys=True, default=str)
    return hashlib.md5(content.encode()).hexdigest()[:12]


def main():
    """Main entry point for sensitivity analysis script."""
    parser = argparse.ArgumentParser(description="Run sensitivity analysis with ±20% parameter variations")
    parser.add_argument("--start-date", type=str, required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--params-path", type=str, help="Path to params.yaml file")
    parser.add_argument("--output-dir", type=str, default="artifacts/sensitivity", help="Output directory")
    parser.add_argument("--campaign-id", type=str, help="Campaign ID (auto-generated if not provided)")
    parser.add_argument("--critical-params", nargs="+", help="Override critical parameters list")
    args = parser.parse_args()
    
    # Load base parameters
    params_path = Path(args.params_path) if args.params_path else None
    base_params = load_base_params(params_path)
    
    # Generate campaign ID
    campaign_id = args.campaign_id or generate_campaign_id(base_params, args.start_date, args.end_date)
    
    # Get critical parameters
    critical_params = args.critical_params or get_critical_params()
    
    # Generate parameter grid with ±20% variations
    param_grid = generate_20pct_variations(base_params, critical_params)
    
    if not param_grid:
        logger.error("No valid parameters found for sensitivity analysis")
        return 1
    
    logger.info(
        "Starting sensitivity analysis",
        extra={
            "campaign_id": campaign_id,
            "start_date": args.start_date,
            "end_date": args.end_date,
            "param_count": len(param_grid),
            "total_combinations": len(pd.MultiIndex.from_product([v for v in param_grid.values()])),
        },
    )
    
    # Run sensitivity analysis
    runner = SensitivityRunner()
    start_dt = pd.to_datetime(args.start_date)
    end_dt = pd.to_datetime(args.end_date)
    
    results_df = runner.run(
        param_grid=param_grid,
        start_date=start_dt,
        end_date=end_dt,
        base_params=base_params,
        use_nested_override=True,
    )
    
    # Add campaign metadata
    results_df["campaign_id"] = campaign_id
    results_df["base_params"] = json.dumps(base_params, default=str)
    results_df["start_date"] = args.start_date
    results_df["end_date"] = args.end_date
    results_df["created_at"] = datetime.utcnow().isoformat()
    
    # Save results
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = output_dir / f"{campaign_id}.parquet"
    results_df.to_parquet(output_path, index=False)
    
    logger.info(
        "Sensitivity analysis completed",
        extra={
            "campaign_id": campaign_id,
            "output_path": str(output_path),
            "total_runs": len(results_df),
            "valid_runs": results_df["valid"].sum() if "valid" in results_df.columns else 0,
        },
    )
    
    # Print summary
    if "calmar" in results_df.columns:
        valid_df = results_df[results_df["valid"] == True] if "valid" in results_df.columns else results_df
        if not valid_df.empty:
            print(f"\nSensitivity Analysis Summary (Campaign: {campaign_id})")
            print(f"Total runs: {len(results_df)}")
            print(f"Valid runs: {len(valid_df)}")
            print(f"Calmar - Mean: {valid_df['calmar'].mean():.3f}, Std: {valid_df['calmar'].std():.3f}")
            print(f"Max DD - Mean: {valid_df['max_dd'].mean():.2f}%, Std: {valid_df['max_dd'].std():.2f}%")
            print(f"Sharpe - Mean: {valid_df['sharpe'].mean():.3f}, Std: {valid_df['sharpe'].std():.3f}")
            print(f"\nResults saved to: {output_path}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

