"""Job to update ensemble strategy weights based on performance metrics."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime

from app.core.database import SessionLocal
from app.core.logging import logger
from app.data.curation import DataCuration
from app.strategies.weight_store import MetaWeightStore
from app.strategies.weight_updater import WeightUpdater


def main():
    """Update ensemble weights for all regimes."""
    parser = argparse.ArgumentParser(description="Update ensemble strategy weights")
    parser.add_argument(
        "--regime",
        type=str,
        choices=["bull", "bear", "range", "neutral", "all"],
        default="all",
        help="Regime to update (default: all)",
    )
    parser.add_argument(
        "--method",
        type=str,
        choices=["softmax_sharpe", "proportional_sharpe", "calmar_weighted"],
        default="softmax_sharpe",
        help="Weight calculation method (default: softmax_sharpe)",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=60,
        help="Number of days to look back for metrics (default: 60)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="artifacts/ensemble",
        help="Directory to save weight artifacts (default: artifacts/ensemble)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Calculate weights but don't save to database",
    )
    args = parser.parse_args()

    logger.info(
        "Starting ensemble weight update",
        extra={
            "regime": args.regime,
            "method": args.method,
            "lookback_days": args.lookback_days,
            "dry_run": args.dry_run,
        },
    )

    session = SessionLocal()
    try:
        weight_store = MetaWeightStore(session=session)
        updater = WeightUpdater(
            session=session,
            weight_store=weight_store,
            lookback_days=args.lookback_days,
        )

        all_weights = {}
        all_metrics = {}

        if args.regime == "all":
            # Update all regimes
            for regime in ["bull", "bear", "range", "neutral"]:
                try:
                    logger.info(f"Updating weights for regime: {regime}")
                    strategy_metrics = updater.calculate_metrics_per_strategy(regime=regime)
                    
                    if not strategy_metrics:
                        logger.warning(f"No metrics found for regime {regime}, skipping")
                        continue
                    
                    weights = updater.calculate_weights(strategy_metrics, method=args.method)
                    
                    if not weights:
                        logger.warning(f"No weights calculated for regime {regime}, skipping")
                        continue
                    
                    if not args.dry_run:
                        snapshot_date = datetime.utcnow().date().isoformat()
                        weight_store.save(
                            regime=regime,
                            weights=weights,
                            metrics=strategy_metrics,
                            snapshot_date=snapshot_date,
                        )
                    
                    all_weights[regime] = weights
                    all_metrics[regime] = strategy_metrics
                    
                    logger.info(
                        f"Updated weights for regime {regime}",
                        extra={"weights": weights},
                    )
                except Exception as exc:
                    logger.error(
                        f"Failed to update weights for regime {regime}",
                        extra={"regime": regime, "error": str(exc)},
                        exc_info=True,
                    )
        else:
            # Update single regime
            try:
                strategy_metrics = updater.calculate_metrics_per_strategy(regime=args.regime)
                
                if not strategy_metrics:
                    logger.error(f"No metrics found for regime {args.regime}")
                    return 1
                
                weights = updater.calculate_weights(strategy_metrics, method=args.method)
                
                if not weights:
                    logger.error(f"No weights calculated for regime {args.regime}")
                    return 1
                
                if not args.dry_run:
                    snapshot_date = datetime.utcnow().date().isoformat()
                    weight_store.save(
                        regime=args.regime,
                        weights=weights,
                        metrics=strategy_metrics,
                        snapshot_date=snapshot_date,
                    )
                
                all_weights[args.regime] = weights
                all_metrics[args.regime] = strategy_metrics
                
                logger.info(
                    f"Updated weights for regime {args.regime}",
                    extra={"weights": weights},
                )
            except Exception as exc:
                logger.error(
                    f"Failed to update weights for regime {args.regime}",
                    extra={"regime": args.regime, "error": str(exc)},
                    exc_info=True,
                )
                return 1

        # Save artifacts
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        artifact = {
            "timestamp": datetime.utcnow().isoformat(),
            "regime": args.regime,
            "method": args.method,
            "lookback_days": args.lookback_days,
            "weights": all_weights,
            "metrics": all_metrics,
            "dry_run": args.dry_run,
        }
        
        artifact_path = output_dir / "weights.json"
        with open(artifact_path, "w") as f:
            json.dump(artifact, f, indent=2, default=str)
        
        logger.info(
            "Ensemble weight update completed",
            extra={
                "artifact_path": str(artifact_path),
                "regimes_updated": list(all_weights.keys()),
            },
        )
        
        return 0
    except Exception as exc:
        logger.error(
            "Ensemble weight update failed",
            extra={"error": str(exc)},
            exc_info=True,
        )
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    import sys
    sys.exit(main())

