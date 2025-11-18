#!/usr/bin/env python3
"""CLI script for SL/TP optimization with walk-forward validation."""
import argparse
import sys
from pathlib import Path

import pandas as pd

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.core.logging import logger
from app.risk import StopLossTakeProfitOptimizer
from app.risk.sl_tp_reporting import SLTPReportGenerator
from app.quant.regime import RegimeClassifier


def load_trades(filepath: str | Path) -> pd.DataFrame:
    """Load trades from parquet or CSV file."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Trades file not found: {filepath}")

    if path.suffix == ".parquet":
        df = pd.read_parquet(path)
    elif path.suffix == ".csv":
        df = pd.read_csv(path)
    else:
        raise ValueError(f"Unsupported file format: {path.suffix}")

    # Ensure required columns exist
    required = ["timestamp", "mae", "mfe"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    return df


def load_price_data(filepath: str | Path | None) -> pd.DataFrame | None:
    """Load price data for regime classification."""
    if filepath is None:
        return None

    path = Path(filepath)
    if not path.exists():
        logger.warning(f"Price data file not found: {filepath}, skipping regime classification")
        return None

    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    elif path.suffix == ".csv":
        return pd.read_csv(path)
    else:
        logger.warning(f"Unsupported price data format: {path.suffix}, skipping")
        return None


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Optimize SL/TP parameters using walk-forward validation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Optimize for BTCUSDT in trend regime
  python scripts/sl_tp/optimize.py --symbol BTCUSDT --regime trend --trades data/backtest_reports/trades.parquet

  # Optimize for all regimes
  python scripts/sl_tp/optimize.py --symbol BTCUSDT --trades data/backtest_reports/trades.parquet --price-data data/curated/1d.parquet

  # Custom search space
  python scripts/sl_tp/optimize.py --symbol BTCUSDT --regime trend --trades trades.parquet \\
    --atr-sl 1.5 2.0 2.5 --atr-tp 2.0 3.0 4.0
        """,
    )

    parser.add_argument(
        "--symbol",
        required=True,
        help="Trading symbol (e.g., BTCUSDT)",
    )
    parser.add_argument(
        "--regime",
        default=None,
        help="Market regime to optimize (if not provided, optimizes all regimes)",
    )
    parser.add_argument(
        "--trades",
        required=True,
        help="Path to trades file (parquet or CSV) with columns: timestamp, mae, mfe",
    )
    parser.add_argument(
        "--price-data",
        default=None,
        help="Path to price data file for regime classification (optional)",
    )
    parser.add_argument(
        "--artifacts-dir",
        default="artifacts/sl_tp",
        help="Directory for optimization artifacts (default: artifacts/sl_tp)",
    )
    parser.add_argument(
        "--reports-dir",
        default="reports",
        help="Directory for generated reports (default: reports)",
    )
    parser.add_argument(
        "--train-days",
        type=int,
        default=90,
        help="Training window size in days (default: 90)",
    )
    parser.add_argument(
        "--test-days",
        type=int,
        default=30,
        help="Test window size in days (default: 30)",
    )
    parser.add_argument(
        "--rr-floor",
        type=float,
        default=1.2,
        help="Minimum RR ratio threshold (default: 1.2)",
    )
    parser.add_argument(
        "--method",
        choices=["grid", "bayesian"],
        default="grid",
        help="Optimization method (default: grid)",
    )
    parser.add_argument(
        "--atr-sl",
        nargs="+",
        type=float,
        help="ATR multiplier values for stop loss (overrides default search space)",
    )
    parser.add_argument(
        "--atr-tp",
        nargs="+",
        type=float,
        help="ATR multiplier values for take profit (overrides default search space)",
    )
    parser.add_argument(
        "--tp-ratio",
        nargs="+",
        type=float,
        help="TP ratio values (overrides default search space)",
    )
    parser.add_argument(
        "--benchmark-rr",
        type=float,
        default=1.5,
        help="Benchmark RR ratio for comparison (default: 1.5)",
    )
    parser.add_argument(
        "--generate-report",
        action="store_true",
        help="Generate markdown report after optimization",
    )

    args = parser.parse_args()

    # Load data
    logger.info(f"Loading trades from {args.trades}")
    trades_df = load_trades(args.trades)

    price_df = None
    regime_classifier = None
    if args.price_data:
        logger.info(f"Loading price data from {args.price_data}")
        price_df = load_price_data(args.price_data)
        if price_df is not None:
            regime_classifier = RegimeClassifier()

    # Build search space if custom values provided
    search_space = None
    if args.atr_sl or args.atr_tp or args.tp_ratio:
        search_space = {}
        if args.atr_sl:
            search_space["atr_multiplier_sl"] = args.atr_sl
        if args.atr_tp:
            search_space["atr_multiplier_tp"] = args.atr_tp
        if args.tp_ratio:
            search_space["tp_ratio"] = args.tp_ratio

    # Initialize optimizer
    optimizer = StopLossTakeProfitOptimizer(
        artifacts_dir=args.artifacts_dir,
        train_days=args.train_days,
        test_days=args.test_days,
        rr_floor=args.rr_floor,
    )

    # Run optimization
    logger.info(f"Starting optimization for {args.symbol}" + (f" (regime: {args.regime})" if args.regime else ""))
    try:
        results = optimizer.optimize(
            trades=trades_df,
            symbol=args.symbol,
            regime_classifier=regime_classifier,
            price_data=price_df,
            search_space=search_space,
            method=args.method,
        )

        if not results:
            logger.error("No optimization results generated")
            return 1

        # Generate reports if requested
        if args.generate_report:
            report_generator = SLTPReportGenerator(
                artifacts_dir=args.artifacts_dir,
                reports_dir=args.reports_dir,
            )

            for regime, config in results.items():
                if args.regime and regime != args.regime:
                    continue

                logger.info(f"Generating report for {args.symbol}/{regime}")
                report = report_generator.generate_report(
                    symbol=args.symbol,
                    regime=regime,
                    windows=config.get("windows", []),
                    consensus_params=config.get("best_params", {}),
                    aggregate_metrics=config.get("aggregates", {}),
                    trades_df=trades_df,
                    benchmark_rr=args.benchmark_rr,
                )
                report_path = report_generator.save_markdown_report(report)
                logger.info(f"Report saved to {report_path}")

        logger.info("Optimization completed successfully")
        return 0

    except Exception as e:
        logger.error(f"Optimization failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

