"""Train meta-learner models for combining strategy signals."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.logging import logger
from app.db.models import SignalOutcomeORM
from app.strategies.meta_learner import MetaLearner


def load_training_data(
    session: Session,
    regime: str | None = None,
    lookback_days: int = 365,
    min_samples: int = 100,
) -> tuple[pd.DataFrame, pd.Series]:
    """
    Load training data from signal_outcomes.
    
    Args:
        session: Database session
        regime: Optional regime filter
        lookback_days: Days to look back
        min_samples: Minimum samples required
    
    Returns:
        Tuple of (X, y) where X is features and y is target (1=BUY win, 0=otherwise)
    """
    cutoff_date = datetime.utcnow() - timedelta(days=lookback_days)

    # Query signal outcomes with outcomes
    stmt = (
        select(SignalOutcomeORM)
        .where(
            and_(
                SignalOutcomeORM.decision_timestamp >= cutoff_date,
                SignalOutcomeORM.outcome.isnot(None),
                SignalOutcomeORM.outcome != "open",
                SignalOutcomeORM.pnl_pct.isnot(None),
            )
        )
        .order_by(SignalOutcomeORM.decision_timestamp)
    )

    if regime:
        stmt = stmt.where(SignalOutcomeORM.market_regime == regime)

    rows = session.execute(stmt).scalars().all()

    if len(rows) < min_samples:
        raise ValueError(
            f"Insufficient samples: {len(rows)} < {min_samples} "
            f"(regime={regime}, lookback_days={lookback_days})"
        )

    # Build feature matrix
    records = []
    for row in rows:
        # Get all signals for this recommendation_id (same timestamp)
        if row.recommendation_id:
            related_signals = session.execute(
                select(SignalOutcomeORM).where(
                    SignalOutcomeORM.recommendation_id == row.recommendation_id
                )
            ).scalars().all()
        else:
            related_signals = [row]

        # Build strategy signals list
        strategy_signals = []
        for sig in related_signals:
            strategy_signals.append({
                "strategy": sig.strategy_id,
                "signal": sig.signal,
                "confidence": sig.confidence_raw,
            })

        # Build regime features
        regime_features = {
            "regime": row.market_regime or "neutral",
            "vol_bucket": row.vol_bucket or "unknown",
            "features_regimen": row.features_regimen or {},
        }

        # Build volatility state (extract from features_regimen if available)
        volatility_state = {}
        if row.features_regimen:
            volatility_state = {
                "volatility": row.features_regimen.get("volatility_30", 0.0),
                "atr": row.features_regimen.get("atr_14", 0.0),
            }

        # Build features using MetaLearner
        learner = MetaLearner()
        try:
            features = learner.build_features(
                strategy_signals,
                regime_features,
                volatility_state,
            )

            # Target: 1 if BUY signal and win, or SELL signal and win (pnl > 0)
            is_win = row.outcome == "win" or (row.pnl_pct is not None and row.pnl_pct > 0)
            is_buy = row.signal == "BUY"
            target = 1 if (is_buy and is_win) or (not is_buy and not is_win and is_win) else 0

            records.append({
                "features": features,
                "target": target,
                "signal": row.signal,
                "outcome": row.outcome,
                "pnl_pct": row.pnl_pct,
            })
        except Exception as exc:
            logger.warning(f"Failed to build features for row {row.id}: {exc}")
            continue

    if len(records) < min_samples:
        raise ValueError(f"Insufficient valid samples after feature building: {len(records)} < {min_samples}")

    # Convert to DataFrame
    df = pd.DataFrame(records)

    # Extract features and target
    X = np.vstack(df["features"].values)
    y = df["target"].values

    logger.info(
        "Loaded training data",
        extra={
            "regime": regime,
            "n_samples": len(X),
            "n_features": X.shape[1],
            "positive_rate": float(np.mean(y)),
        },
    )

    return pd.DataFrame(X), pd.Series(y)


def train_model(
    X: pd.DataFrame,
    y: pd.Series,
    model_type: str = "logistic",
    regime: str | None = None,
) -> tuple[MetaLearner, dict[str, float]]:
    """
    Train meta-learner model.
    
    Args:
        X: Feature matrix
        y: Target labels
        model_type: Model type
        regime: Regime name
    
    Returns:
        Tuple of (trained_model, metrics)
    """
    learner = MetaLearner(model_type=model_type, regime=regime)
    metrics = learner.fit(X, y)

    return learner, metrics


def main():
    """Train meta-learner models."""
    parser = argparse.ArgumentParser(description="Train meta-learner for ensemble")
    parser.add_argument(
        "--regime",
        type=str,
        choices=["bull", "bear", "range", "neutral", "all"],
        default="all",
        help="Regime to train for (default: all)",
    )
    parser.add_argument(
        "--model-type",
        type=str,
        choices=["logistic", "gradient_boosting"],
        default="logistic",
        help="Model type (default: logistic)",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=365,
        help="Days to look back for training data (default: 365)",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=100,
        help="Minimum samples required (default: 100)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="artifacts/meta_learner",
        help="Output directory for models (default: artifacts/meta_learner)",
    )
    args = parser.parse_args()

    logger.info(
        "Starting meta-learner training",
        extra={
            "regime": args.regime,
            "model_type": args.model_type,
            "lookback_days": args.lookback_days,
        },
    )

    session = SessionLocal()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {}

    try:
        regimes_to_train = ["bull", "bear", "range", "neutral"] if args.regime == "all" else [args.regime]

        for regime in regimes_to_train:
            try:
                logger.info(f"Training model for regime: {regime}")

                # Load data
                X, y = load_training_data(
                    session,
                    regime=regime if regime != "all" else None,
                    lookback_days=args.lookback_days,
                    min_samples=args.min_samples,
                )

                # Train model
                learner, metrics = train_model(X, y, model_type=args.model_type, regime=regime)

                # Save model
                model_path = output_dir / regime / "model.pkl"
                learner.save(model_path)

                # Save metrics report
                report = {
                    "regime": regime,
                    "model_type": args.model_type,
                    "trained_at": datetime.utcnow().isoformat(),
                    "metrics": metrics,
                    "n_samples": len(X),
                    "n_features": X.shape[1],
                    "positive_rate": float(np.mean(y)),
                    "model_path": str(model_path),
                }

                report_path = output_dir / regime / "metrics.json"
                report_path.parent.mkdir(parents=True, exist_ok=True)
                with open(report_path, "w") as f:
                    json.dump(report, f, indent=2, default=str)

                results[regime] = report

                logger.info(
                    f"Trained model for regime {regime}",
                    extra={"metrics": metrics, "model_path": str(model_path)},
                )
            except ValueError as exc:
                logger.warning(f"Skipping regime {regime}: {exc}")
                results[regime] = {"error": str(exc)}
            except Exception as exc:
                logger.error(
                    f"Failed to train model for regime {regime}",
                    extra={"error": str(exc)},
                    exc_info=True,
                )
                results[regime] = {"error": str(exc)}

        # Save summary
        summary_path = output_dir / "training_summary.json"
        summary = {
            "trained_at": datetime.utcnow().isoformat(),
            "model_type": args.model_type,
            "lookback_days": args.lookback_days,
            "results": results,
        }
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2, default=str)

        logger.info(
            "Meta-learner training completed",
            extra={"summary_path": str(summary_path)},
        )

        return 0
    except Exception as exc:
        logger.error(
            "Meta-learner training failed",
            extra={"error": str(exc)},
            exc_info=True,
        )
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    import sys
    sys.exit(main())

