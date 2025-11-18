"""Meta-weight store for ensemble strategy weights."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import select, and_, desc

from app.core.database import SessionLocal
from app.core.logging import logger
from app.db.models import EnsembleWeightORM


class MetaWeightStore:
    """Store and retrieve ensemble strategy weights by regime."""

    def __init__(self, session: Session | None = None):
        """
        Initialize weight store.
        
        Args:
            session: Optional database session (creates new if None)
        """
        self.session = session

    def _get_session(self) -> Session:
        """Get database session."""
        if self.session is not None:
            return self.session
        return SessionLocal()

    def _close_session(self, session: Session) -> None:
        """Close session if it was created by this store."""
        if self.session is None:
            session.close()

    def save(
        self,
        regime: str,
        weights: dict[str, float],
        metrics: dict[str, dict[str, float]],
        snapshot_date: str | None = None,
    ) -> None:
        """
        Save weights for a regime.
        
        Args:
            regime: Market regime (bull|bear|range|neutral)
            weights: Dict mapping strategy_name -> weight
            metrics: Dict mapping strategy_name -> metrics dict (calmar, drawdown, hit_rate, etc.)
            snapshot_date: Date string YYYY-MM-DD (defaults to today)
        """
        if snapshot_date is None:
            snapshot_date = datetime.utcnow().date().isoformat()

        session = self._get_session()
        try:
            # Deactivate old weights for this regime
            stmt = (
                select(EnsembleWeightORM)
                .where(
                    and_(
                        EnsembleWeightORM.regime == regime,
                        EnsembleWeightORM.is_active == True,
                    )
                )
            )
            old_weights = session.execute(stmt).scalars().all()
            for old_weight in old_weights:
                old_weight.is_active = False

            # Save new weights
            for strategy_name, weight in weights.items():
                strategy_metrics = metrics.get(strategy_name, {})
                weight_record = EnsembleWeightORM(
                    regime=regime,
                    strategy_name=strategy_name,
                    weight=weight,
                    snapshot_date=snapshot_date,
                    metrics=strategy_metrics,
                    is_active=True,
                )
                session.add(weight_record)

            session.commit()
            logger.info(
                "Saved ensemble weights",
                extra={
                    "regime": regime,
                    "snapshot_date": snapshot_date,
                    "weights": weights,
                },
            )
        except Exception as exc:
            session.rollback()
            logger.error(
                "Failed to save ensemble weights",
                extra={"regime": regime, "error": str(exc)},
                exc_info=True,
            )
            raise
        finally:
            self._close_session(session)

    def load(
        self,
        regime: str | None = None,
        fallback_to_latest: bool = True,
    ) -> dict[str, float] | None:
        """
        Load active weights for a regime.
        
        Args:
            regime: Market regime (bull|bear|range|neutral). If None, uses 'neutral'
            fallback_to_latest: If True and no weights for regime, return latest weights for any regime
        
        Returns:
            Dict mapping strategy_name -> weight, or None if no weights found
        """
        if regime is None:
            regime = "neutral"

        session = self._get_session()
        try:
            # Try to load weights for the specified regime
            stmt = (
                select(EnsembleWeightORM)
                .where(
                    and_(
                        EnsembleWeightORM.regime == regime,
                        EnsembleWeightORM.is_active == True,
                    )
                )
                .order_by(desc(EnsembleWeightORM.calculated_at))
            )
            weights_records = session.execute(stmt).scalars().all()

            if not weights_records and fallback_to_latest:
                # Fallback: get latest weights for any regime
                stmt = (
                    select(EnsembleWeightORM)
                    .where(EnsembleWeightORM.is_active == True)
                    .order_by(desc(EnsembleWeightORM.calculated_at))
                )
                weights_records = session.execute(stmt).scalars().all()

                # Group by regime and get the most recent regime's weights
                if weights_records:
                    latest_regime = weights_records[0].regime
                    stmt = (
                        select(EnsembleWeightORM)
                        .where(
                            and_(
                                EnsembleWeightORM.regime == latest_regime,
                                EnsembleWeightORM.is_active == True,
                            )
                        )
                        .order_by(desc(EnsembleWeightORM.calculated_at))
                    )
                    weights_records = session.execute(stmt).scalars().all()
                    logger.info(
                        f"No weights for regime '{regime}', using latest from '{latest_regime}'",
                        extra={"requested_regime": regime, "fallback_regime": latest_regime},
                    )

            if not weights_records:
                return None

            # Build weights dict
            weights = {record.strategy_name: record.weight for record in weights_records}

            logger.debug(
                "Loaded ensemble weights",
                extra={
                    "regime": regime,
                    "weights": weights,
                    "count": len(weights),
                },
            )
            return weights
        except Exception as exc:
            logger.error(
                "Failed to load ensemble weights",
                extra={"regime": regime, "error": str(exc)},
                exc_info=True,
            )
            return None
        finally:
            self._close_session(session)

    def get_history(
        self,
        regime: str | None = None,
        days: int = 90,
    ) -> list[dict[str, Any]]:
        """
        Get weight history for a regime.
        
        Args:
            regime: Market regime (None for all regimes)
            days: Number of days to look back
        
        Returns:
            List of weight snapshots with metadata
        """
        session = self._get_session()
        try:
            cutoff_date = (datetime.utcnow() - timedelta(days=days)).date().isoformat()

            stmt = (
                select(EnsembleWeightORM)
                .where(EnsembleWeightORM.snapshot_date >= cutoff_date)
                .order_by(desc(EnsembleWeightORM.calculated_at))
            )

            if regime:
                stmt = stmt.where(EnsembleWeightORM.regime == regime)

            records = session.execute(stmt).scalars().all()

            history = []
            for record in records:
                history.append({
                    "regime": record.regime,
                    "strategy_name": record.strategy_name,
                    "weight": record.weight,
                    "snapshot_date": record.snapshot_date,
                    "metrics": record.metrics,
                    "calculated_at": record.calculated_at.isoformat(),
                    "is_active": record.is_active,
                })

            return history
        except Exception as exc:
            logger.error(
                "Failed to get weight history",
                extra={"regime": regime, "error": str(exc)},
                exc_info=True,
            )
            return []
        finally:
            self._close_session(session)

