"""Trade activity ledger for tracking daily trade activity and risk limits."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from app.core.database import SessionLocal
from app.core.logging import logger
from app.db.models import RecommendationORM
from sqlalchemy import select, and_
from sqlalchemy.orm import Session


@dataclass
class TradeActivitySummary:
    """Summary of trade activity in the last 24 hours."""

    user_id: str
    trades_count: int
    trades_remaining: int
    max_trades_24h: int
    is_at_limit: bool
    committed_risk_pct: float  # Total risk committed today as % of equity
    committed_risk_amount: float  # Total risk committed today in absolute terms
    daily_risk_limit_pct: float  # Daily risk limit (3%)
    daily_risk_warning_pct: float  # Daily risk warning threshold (2%)


class TradeActivityLedger:
    """Service for tracking trade activity and daily risk limits."""

    def __init__(self, session: Session | None = None):
        """Initialize service."""
        self.session = session

    def get_trades_last_24h(
        self,
        user_id: str | UUID,
        *,
        now: datetime | None = None,
    ) -> list[RecommendationORM]:
        """
        Get all trades (closed recommendations) in the last 24 hours.
        
        Args:
            user_id: User ID
            now: Current timestamp (default: datetime.utcnow())
            
        Returns:
            List of RecommendationORM records closed in last 24h
        """
        if now is None:
            now = datetime.utcnow()
        
        last_24h = now - timedelta(hours=24)
        
        db = self.session or SessionLocal()
        try:
            user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
            
            # Get all closed recommendations in last 24h
            # Note: In single-user system, we don't filter by user_id in recommendations table
            # In multi-user system, would add: .where(RecommendationORM.user_id == user_uuid)
            stmt = (
                select(RecommendationORM)
                .where(RecommendationORM.status == "closed")
                .where(RecommendationORM.closed_at.isnot(None))
                .where(RecommendationORM.closed_at >= last_24h)
                .order_by(RecommendationORM.closed_at.desc())
            )
            
            trades = list(db.execute(stmt).scalars().all())
            return trades
        except Exception as e:
            logger.error(f"Error fetching trades in last 24h: {e}", exc_info=True)
            return []
        finally:
            if not self.session:
                db.close()

    def get_activity_summary(
        self,
        user_id: str | UUID,
        user_equity: float,
        max_trades_24h: int,
        *,
        now: datetime | None = None,
    ) -> TradeActivitySummary:
        """
        Get summary of trade activity in last 24 hours.
        
        Args:
            user_id: User ID
            user_equity: User's current equity
            max_trades_24h: Maximum allowed trades in 24h
            now: Current timestamp (default: datetime.utcnow())
            
        Returns:
            TradeActivitySummary with activity metrics
        """
        trades = self.get_trades_last_24h(user_id, now=now)
        trades_count = len(trades)
        
        # Calculate committed risk from closed trades today
        # Risk is calculated from risk_metrics if available, otherwise estimate
        committed_risk_amount = 0.0
        for trade in trades:
            risk_metrics = trade.risk_metrics or {}
            if "risk_pct" in risk_metrics:
                # Use actual risk percentage from trade
                risk_pct = risk_metrics["risk_pct"]
                # Estimate equity at time of trade (simplified: use current equity)
                # In production, would track equity at time of trade
                committed_risk_amount += user_equity * (risk_pct / 100.0)
            elif "suggested_sizing" in risk_metrics:
                sizing = risk_metrics["suggested_sizing"]
                if "risk_amount" in sizing:
                    committed_risk_amount += sizing["risk_amount"]
                elif "risk_pct" in sizing:
                    committed_risk_amount += user_equity * (sizing["risk_pct"] / 100.0)
            else:
                # Fallback: estimate 1% risk per trade
                committed_risk_amount += user_equity * 0.01
        
        committed_risk_pct = (committed_risk_amount / user_equity * 100.0) if user_equity > 0 else 0.0
        
        trades_remaining = max(0, max_trades_24h - trades_count)
        is_at_limit = trades_count >= max_trades_24h
        
        return TradeActivitySummary(
            user_id=str(user_id),
            trades_count=trades_count,
            trades_remaining=trades_remaining,
            max_trades_24h=max_trades_24h,
            is_at_limit=is_at_limit,
            committed_risk_pct=committed_risk_pct,
            committed_risk_amount=committed_risk_amount,
            daily_risk_limit_pct=3.0,  # 3% daily limit
            daily_risk_warning_pct=2.0,  # 2% warning threshold
        )

    def can_trade(
        self,
        user_id: str | UUID,
        user_equity: float,
        max_trades_24h: int,
        *,
        now: datetime | None = None,
    ) -> tuple[bool, str | None]:
        """
        Check if user can execute a new trade (preventive check).
        
        Args:
            user_id: User ID
            user_equity: User's current equity
            max_trades_24h: Maximum allowed trades in 24h
            now: Current timestamp (default: datetime.utcnow())
            
        Returns:
            Tuple of (can_trade: bool, reason: str | None)
        """
        summary = self.get_activity_summary(user_id, user_equity, max_trades_24h, now=now)
        
        # Preventive check: block if at limit - 1 (so user can't reach the limit)
        if summary.trades_count >= (max_trades_24h - 1):
            remaining = summary.trades_remaining
            return False, f"Límite preventivo: has ejecutado {summary.trades_count} trades en las últimas 24h. Te quedan {remaining} operaciones antes del límite diario ({max_trades_24h})."
        
        return True, None

