"""Store and retrieve strategy performance metrics for correlation analysis."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import select, and_, func
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.logging import logger
from app.db.models import SignalOutcomeORM


class StrategyPerformanceStore:
    """Store and retrieve strategy performance metrics for analysis."""

    def __init__(self, session: Session | None = None):
        """
        Initialize performance store.
        
        Args:
            session: Optional database session
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

    def get_strategy_returns(
        self,
        strategy_names: list[str],
        window_days: int = 30,
        regime: str | None = None,
    ) -> pd.DataFrame:
        """
        Get rolling returns for strategies.
        
        Args:
            strategy_names: List of strategy names
            window_days: Rolling window in days
            regime: Optional regime filter
        
        Returns:
            DataFrame with columns: strategy_name, date, return_pct
        """
        session = self._get_session()
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=window_days)

            stmt = (
                select(
                    SignalOutcomeORM.strategy_id,
                    SignalOutcomeORM.decision_timestamp,
                    SignalOutcomeORM.pnl_pct,
                    SignalOutcomeORM.outcome,
                )
                .where(
                    and_(
                        SignalOutcomeORM.decision_timestamp >= cutoff_date,
                        SignalOutcomeORM.strategy_id.in_(strategy_names),
                        SignalOutcomeORM.outcome.isnot(None),
                        SignalOutcomeORM.outcome != "open",
                        SignalOutcomeORM.pnl_pct.isnot(None),
                    )
                )
                .order_by(SignalOutcomeORM.decision_timestamp)
            )

            if regime:
                stmt = stmt.where(SignalOutcomeORM.market_regime == regime)

            rows = session.execute(stmt).all()

            if not rows:
                logger.warning(
                    "No strategy returns found",
                    extra={"strategies": strategy_names, "window_days": window_days},
                )
                return pd.DataFrame(columns=["strategy_name", "date", "return_pct"])

            # Build DataFrame
            records = []
            for row in rows:
                records.append({
                    "strategy_name": row.strategy_id,
                    "date": row.decision_timestamp.date(),
                    "return_pct": float(row.pnl_pct or 0.0),
                })

            df = pd.DataFrame(records)

            # Pivot to get returns by strategy
            if df.empty:
                return pd.DataFrame(columns=["strategy_name", "date", "return_pct"])

            # Group by date and strategy, take mean return per day
            df_grouped = df.groupby(["date", "strategy_name"])["return_pct"].mean().reset_index()

            return df_grouped
        except Exception as exc:
            logger.error(
                "Failed to get strategy returns",
                extra={"error": str(exc)},
                exc_info=True,
            )
            return pd.DataFrame(columns=["strategy_name", "date", "return_pct"])
        finally:
            self._close_session(session)

    def calculate_correlation_matrix(
        self,
        strategy_names: list[str],
        window_days: int = 30,
        regime: str | None = None,
    ) -> dict[str, dict[str, float]]:
        """
        Calculate correlation matrix between strategies.
        
        Args:
            strategy_names: List of strategy names
            window_days: Rolling window in days
            regime: Optional regime filter
        
        Returns:
            Dict mapping strategy_name -> dict of correlations with other strategies
        """
        df = self.get_strategy_returns(strategy_names, window_days, regime)

        if df.empty or len(strategy_names) < 2:
            # Return zero correlations if no data
            return {name: {other: 0.0 for other in strategy_names if other != name} for name in strategy_names}

        # Pivot to get returns matrix
        try:
            df_pivot = df.pivot(index="date", columns="strategy_name", values="return_pct")
            df_pivot = df_pivot.fillna(0.0)  # Fill missing with 0

            # Calculate correlation
            corr_matrix = df_pivot.corr()

            # Build result dict
            result = {}
            for strategy in strategy_names:
                result[strategy] = {}
                for other in strategy_names:
                    if strategy == other:
                        continue
                    if strategy in corr_matrix.index and other in corr_matrix.columns:
                        corr = float(corr_matrix.loc[strategy, other])
                        result[strategy][other] = corr if not np.isnan(corr) else 0.0
                    else:
                        result[strategy][other] = 0.0

            return result
        except Exception as exc:
            logger.warning(
                "Failed to calculate correlation matrix",
                extra={"error": str(exc)},
            )
            return {name: {other: 0.0 for other in strategy_names if other != name} for name in strategy_names}

    def get_strategy_mae_mfe(
        self,
        strategy_name: str,
        window_days: int = 60,
        regime: str | None = None,
    ) -> dict[str, float]:
        """
        Get historical MAE/MFE metrics for a strategy.
        
        Args:
            strategy_name: Strategy name
            window_days: Rolling window in days
            regime: Optional regime filter
        
        Returns:
            Dict with mae_pct, mfe_pct, rr_expected
        """
        session = self._get_session()
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=window_days)

            # Get signal outcomes with metadata containing MAE/MFE
            stmt = (
                select(SignalOutcomeORM)
                .where(
                    and_(
                        SignalOutcomeORM.strategy_id == strategy_name,
                        SignalOutcomeORM.decision_timestamp >= cutoff_date,
                        SignalOutcomeORM.outcome.isnot(None),
                        SignalOutcomeORM.outcome != "open",
                    )
                )
                .order_by(SignalOutcomeORM.decision_timestamp)
            )

            if regime:
                stmt = stmt.where(SignalOutcomeORM.market_regime == regime)

            rows = session.execute(stmt).scalars().all()

            if not rows:
                return {
                    "mae_pct": 0.0,
                    "mfe_pct": 0.0,
                    "rr_expected": 0.0,
                }

            # Extract MAE/MFE from metadata
            mae_values = []
            mfe_values = []

            for row in rows:
                metadata = row.metadata or {}
                trade_efficiency = metadata.get("trade_efficiency", {})
                metrics = trade_efficiency.get("metrics", {})

                mae_pct = metrics.get("mae_pct")
                mfe_pct = metrics.get("mfe_pct")

                if mae_pct is not None:
                    mae_values.append(float(mae_pct))
                if mfe_pct is not None:
                    mfe_values.append(float(mfe_pct))

            # Calculate percentiles
            if mae_values:
                mae_p70 = float(np.percentile(mae_values, 70))
            else:
                mae_p70 = 0.0

            if mfe_values:
                mfe_p50 = float(np.percentile(mfe_values, 50))
            else:
                mfe_p50 = 0.0

            # Calculate expected RR
            rr_expected = mfe_p50 / mae_p70 if mae_p70 > 0 else 0.0

            return {
                "mae_pct": mae_p70,
                "mfe_pct": mfe_p50,
                "rr_expected": rr_expected,
            }
        except Exception as exc:
            logger.warning(
                f"Failed to get MAE/MFE for strategy {strategy_name}",
                extra={"error": str(exc)},
            )
            return {
                "mae_pct": 0.0,
                "mfe_pct": 0.0,
                "rr_expected": 0.0,
            }
        finally:
            self._close_session(session)

