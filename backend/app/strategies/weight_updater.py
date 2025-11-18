"""Weight updater that calculates ensemble weights based on performance metrics."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.db.crud import get_recommendation_history
from app.db.models import SignalOutcomeORM
from app.quant.regime import RegimeClassifier
from app.strategies.weight_store import MetaWeightStore


class WeightUpdater:
    """Calculate and update ensemble weights based on strategy performance."""

    def __init__(
        self,
        session: Session | None = None,
        weight_store: MetaWeightStore | None = None,
        lookback_days: int = 60,
    ):
        """
        Initialize weight updater.
        
        Args:
            session: Optional database session
            weight_store: Optional weight store (creates new if None)
            lookback_days: Number of days to look back for performance metrics
        """
        self.session = session
        self.weight_store = weight_store or MetaWeightStore(session=session)
        self.lookback_days = lookback_days

    def calculate_metrics_per_strategy(
        self,
        regime: str | None = None,
    ) -> dict[str, dict[str, float]]:
        """
        Calculate performance metrics per strategy from signal outcomes.
        
        Args:
            regime: Optional regime filter
        
        Returns:
            Dict mapping strategy_name -> metrics dict
        """
        if self.session is None:
            from app.core.database import SessionLocal
            session = SessionLocal()
            should_close = True
        else:
            session = self.session
            should_close = False

        try:
            cutoff_date = datetime.utcnow() - timedelta(days=self.lookback_days)

            # Query signal outcomes
            from sqlalchemy import select, and_, func

            stmt = (
                select(
                    SignalOutcomeORM.strategy_id,
                    func.count(SignalOutcomeORM.id).label("total_signals"),
                    func.sum(
                        func.case((SignalOutcomeORM.outcome == "win", 1), else_=0)
                    ).label("wins"),
                    func.avg(SignalOutcomeORM.pnl_pct).label("avg_pnl"),
                    func.stddev(SignalOutcomeORM.pnl_pct).label("std_pnl"),
                    func.min(SignalOutcomeORM.pnl_pct).label("min_pnl"),
                    func.max(SignalOutcomeORM.pnl_pct).label("max_pnl"),
                )
                .where(
                    and_(
                        SignalOutcomeORM.decision_timestamp >= cutoff_date,
                        SignalOutcomeORM.outcome.isnot(None),
                        SignalOutcomeORM.pnl_pct.isnot(None),
                    )
                )
                .group_by(SignalOutcomeORM.strategy_id)
            )

            if regime:
                stmt = stmt.where(SignalOutcomeORM.market_regime == regime)

            results = session.execute(stmt).all()

            strategy_metrics = {}
            for row in results:
                strategy_id = row.strategy_id
                total = row.total_signals or 0
                wins = row.wins or 0
                avg_pnl = float(row.avg_pnl or 0.0)
                std_pnl = float(row.std_pnl or 0.0) if row.std_pnl is not None else 0.0
                min_pnl = float(row.min_pnl or 0.0)
                max_pnl = float(row.max_pnl or 0.0)

                # Calculate metrics
                hit_rate = (wins / total * 100.0) if total > 0 else 0.0

                # Sharpe-like metric (annualized, simplified)
                sharpe = (avg_pnl / std_pnl * np.sqrt(252)) if std_pnl > 0 else 0.0

                # Drawdown estimate (max negative streak)
                # For simplicity, use min_pnl as proxy for max drawdown
                max_drawdown = abs(min_pnl) if min_pnl < 0 else 0.0

                # Calmar-like metric (return / max_drawdown)
                calmar = (avg_pnl / max_drawdown) if max_drawdown > 0 else 0.0

                strategy_metrics[strategy_id] = {
                    "total_signals": total,
                    "wins": wins,
                    "hit_rate": hit_rate,
                    "avg_pnl": avg_pnl,
                    "std_pnl": std_pnl,
                    "sharpe": sharpe,
                    "max_drawdown": max_drawdown,
                    "calmar": calmar,
                    "min_pnl": min_pnl,
                    "max_pnl": max_pnl,
                }

            logger.info(
                "Calculated strategy metrics",
                extra={
                    "regime": regime,
                    "strategies": list(strategy_metrics.keys()),
                    "lookback_days": self.lookback_days,
                },
            )
            return strategy_metrics
        except Exception as exc:
            logger.error(
                "Failed to calculate strategy metrics",
                extra={"regime": regime, "error": str(exc)},
                exc_info=True,
            )
            return {}
        finally:
            if should_close:
                session.close()

    def calculate_weights(
        self,
        strategy_metrics: dict[str, dict[str, float]],
        method: str = "softmax_sharpe",
    ) -> dict[str, float]:
        """
        Calculate normalized weights from strategy metrics.
        
        Args:
            strategy_metrics: Dict mapping strategy_name -> metrics
            method: Weighting method:
                - "softmax_sharpe": Softmax of Sharpe penalized by drawdown
                - "proportional_sharpe": Proportional to max(0, Sharpe)
                - "calmar_weighted": Proportional to max(0, Calmar)
        
        Returns:
            Dict mapping strategy_name -> normalized weight
        """
        if not strategy_metrics:
            return {}

        strategy_names = list(strategy_metrics.keys())
        scores = []

        for strategy_name in strategy_names:
            metrics = strategy_metrics[strategy_name]
            
            if method == "softmax_sharpe":
                # Softmax of Sharpe penalized by drawdown
                sharpe = metrics.get("sharpe", 0.0)
                max_dd = metrics.get("max_drawdown", 0.0)
                # Penalize high drawdown: score = sharpe * (1 - normalized_dd)
                # Normalize drawdown to 0-1 range (assuming max reasonable DD is 50%)
                normalized_dd = min(max_dd / 50.0, 1.0) if max_dd > 0 else 0.0
                score = sharpe * (1.0 - normalized_dd * 0.5)  # Reduce by up to 50%
                # Ensure non-negative
                score = max(score, 0.0)
                scores.append(score)
            
            elif method == "proportional_sharpe":
                sharpe = metrics.get("sharpe", 0.0)
                scores.append(max(sharpe, 0.0))
            
            elif method == "calmar_weighted":
                calmar = metrics.get("calmar", 0.0)
                scores.append(max(calmar, 0.0))
            
            else:
                # Default: equal weights
                scores.append(1.0)

        # Normalize using softmax for softmax_sharpe, otherwise proportional
        if method == "softmax_sharpe":
            # Softmax with temperature
            temperature = 1.0
            exp_scores = np.exp(np.array(scores) / temperature)
            weights = exp_scores / exp_scores.sum()
        else:
            # Proportional normalization
            total_score = sum(scores)
            if total_score > 0:
                weights = np.array(scores) / total_score
            else:
                # Fallback to equal weights
                weights = np.ones(len(scores)) / len(scores)

        # Build weights dict
        result = {name: float(weight) for name, weight in zip(strategy_names, weights)}

        logger.info(
            "Calculated weights",
            extra={
                "method": method,
                "weights": result,
                "scores": {name: float(score) for name, score in zip(strategy_names, scores)},
            },
        )
        return result

    def detect_regime(self, df_1d) -> str:
        """
        Detect current market regime.
        
        Args:
            df_1d: Daily price dataframe
        
        Returns:
            Regime string (bull|bear|range|neutral)
        """
        try:
            classifier = RegimeClassifier(method="hmm", n_regimes=3)
            regime_proba = classifier.fit_predict_proba(df_1d)
            
            if regime_proba.empty:
                return "neutral"
            
            latest = regime_proba.iloc[-1]
            
            # Map HMM regimes to labels
            # Assuming: 0=calm, 1=balanced, 2=stress
            # We'll map to: calm->bull, balanced->range, stress->bear
            if "stress" in latest.index:
                p_stress = latest.get("stress", 0.0)
                p_calm = latest.get("calm", 0.0)
                p_balanced = latest.get("balanced", 0.0)
                
                if p_stress > 0.5:
                    return "bear"
                elif p_calm > 0.5:
                    return "bull"
                elif p_balanced > 0.4:
                    return "range"
                else:
                    return "neutral"
            else:
                # Fallback: use volatility-based regime
                returns = df_1d["close"].pct_change().dropna()
                if len(returns) < 20:
                    return "neutral"
                
                vol = returns.std()
                mean_ret = returns.mean()
                
                if mean_ret > 0.001 and vol < 0.03:
                    return "bull"
                elif mean_ret < -0.001 and vol > 0.04:
                    return "bear"
                elif vol < 0.025:
                    return "range"
                else:
                    return "neutral"
        except Exception as exc:
            logger.warning(
                "Failed to detect regime, using neutral",
                extra={"error": str(exc)},
            )
            return "neutral"

    def update_weights_for_regime(
        self,
        regime: str,
        method: str = "softmax_sharpe",
    ) -> dict[str, float]:
        """
        Calculate and save weights for a specific regime.
        
        Args:
            regime: Market regime (bull|bear|range|neutral)
            method: Weighting method
        
        Returns:
            Dict of calculated weights
        """
        # Calculate metrics
        strategy_metrics = self.calculate_metrics_per_strategy(regime=regime)
        
        if not strategy_metrics:
            logger.warning(
                "No strategy metrics found, cannot update weights",
                extra={"regime": regime},
            )
            return {}

        # Calculate weights
        weights = self.calculate_weights(strategy_metrics, method=method)

        if not weights:
            logger.warning(
                "No weights calculated",
                extra={"regime": regime},
            )
            return {}

        # Save weights
        snapshot_date = datetime.utcnow().date().isoformat()
        self.weight_store.save(
            regime=regime,
            weights=weights,
            metrics=strategy_metrics,
            snapshot_date=snapshot_date,
        )

        return weights

    def update_all_regimes(
        self,
        method: str = "softmax_sharpe",
    ) -> dict[str, dict[str, float]]:
        """
        Update weights for all regimes.
        
        Args:
            method: Weighting method
        
        Returns:
            Dict mapping regime -> weights dict
        """
        regimes = ["bull", "bear", "range", "neutral"]
        all_weights = {}

        for regime in regimes:
            try:
                weights = self.update_weights_for_regime(regime, method=method)
                if weights:
                    all_weights[regime] = weights
            except Exception as exc:
                logger.error(
                    f"Failed to update weights for regime {regime}",
                    extra={"regime": regime, "error": str(exc)},
                    exc_info=True,
                )

        return all_weights

