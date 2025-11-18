"""Exposure ledger service for tracking positions and calculating aggregate exposure."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.core.database import SessionLocal
from app.core.logging import logger
from app.db.models import ExposureLedgerORM
from sqlalchemy import select
from sqlalchemy.orm import Session


@dataclass
class ExposureSummary:
    """Summary of user's aggregate exposure."""

    user_id: str
    total_notional: float
    beta_adjusted_notional: float
    position_count: int
    positions: list[dict[str, Any]]
    current_exposure_multiplier: float  # beta_adjusted_notional / equity
    limit_exposure_multiplier: float  # Configurable limit (default: 2.0)


class ExposureLedgerService:
    """Service for managing exposure ledger and calculating aggregate exposure."""

    def __init__(self, session: Session | None = None):
        """Initialize service."""
        self.session = session

    def add_position(
        self,
        user_id: str | UUID,
        recommendation_id: int,
        symbol: str,
        direction: str,
        notional: float,
        entry_price: float,
        beta_value: float = 1.0,
        beta_bucket: str | None = None,
    ) -> ExposureLedgerORM:
        """
        Add a new position to the exposure ledger.
        
        Args:
            user_id: User ID
            recommendation_id: Recommendation ID
            symbol: Trading symbol
            direction: BUY or SELL
            notional: Position notional value
            entry_price: Entry price
            beta_value: Beta vs market (default: 1.0)
            beta_bucket: Beta bucket category (low|medium|high)
            
        Returns:
            Created ExposureLedgerORM record
        """
        db = self.session or SessionLocal()
        try:
            user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
            
            # Determine beta bucket if not provided
            if beta_bucket is None:
                if beta_value < 0.5:
                    beta_bucket = "low"
                elif beta_value < 1.5:
                    beta_bucket = "medium"
                else:
                    beta_bucket = "high"
            
            ledger_entry = ExposureLedgerORM(
                user_id=user_uuid,
                recommendation_id=recommendation_id,
                symbol=symbol,
                direction=direction,
                notional=notional,
                entry_price=entry_price,
                beta_value=beta_value,
                beta_bucket=beta_bucket,
                is_active=True,
            )
            
            db.add(ledger_entry)
            db.commit()
            db.refresh(ledger_entry)
            
            logger.info(
                f"Added position to exposure ledger: user={user_id}, symbol={symbol}, "
                f"notional={notional:.2f}, beta={beta_value:.2f}"
            )
            
            return ledger_entry
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to add position to exposure ledger: {e}", exc_info=True)
            raise
        finally:
            if not self.session:
                db.close()

    def close_position(
        self,
        user_id: str | UUID,
        recommendation_id: int,
    ) -> None:
        """
        Mark a position as closed in the exposure ledger.
        
        Args:
            user_id: User ID
            recommendation_id: Recommendation ID
        """
        db = self.session or SessionLocal()
        try:
            user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
            
            stmt = (
                select(ExposureLedgerORM)
                .where(ExposureLedgerORM.user_id == user_uuid)
                .where(ExposureLedgerORM.recommendation_id == recommendation_id)
                .where(ExposureLedgerORM.is_active == True)
            )
            entry = db.execute(stmt).scalars().first()
            
            if entry:
                entry.is_active = False
                from datetime import datetime
                entry.closed_at = datetime.utcnow()
                db.commit()
                logger.info(f"Closed position in exposure ledger: recommendation_id={recommendation_id}")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to close position in exposure ledger: {e}", exc_info=True)
        finally:
            if not self.session:
                db.close()

    def get_active_positions(
        self,
        user_id: str | UUID,
    ) -> list[ExposureLedgerORM]:
        """
        Get all active positions for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            List of active ExposureLedgerORM records
        """
        db = self.session or SessionLocal()
        try:
            user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
            
            stmt = (
                select(ExposureLedgerORM)
                .where(ExposureLedgerORM.user_id == user_uuid)
                .where(ExposureLedgerORM.is_active == True)
            )
            positions = list(db.execute(stmt).scalars().all())
            
            return positions
        except Exception as e:
            logger.error(f"Failed to get active positions: {e}", exc_info=True)
            return []
        finally:
            if not self.session:
                db.close()

    def calculate_exposure_summary(
        self,
        user_id: str | UUID,
        user_equity: float,
        limit_multiplier: float = 2.0,
    ) -> ExposureSummary:
        """
        Calculate aggregate exposure summary for a user.
        
        Args:
            user_id: User ID
            user_equity: User's current equity
            limit_multiplier: Maximum allowed exposure multiplier (default: 2.0)
            
        Returns:
            ExposureSummary with aggregate metrics
        """
        positions = self.get_active_positions(user_id)
        
        total_notional = sum(pos.notional for pos in positions)
        beta_adjusted_notional = sum(pos.notional * abs(pos.beta_value) for pos in positions)
        
        positions_data = [
            {
                "recommendation_id": pos.recommendation_id,
                "symbol": pos.symbol,
                "direction": pos.direction,
                "notional": pos.notional,
                "beta_value": pos.beta_value,
                "beta_bucket": pos.beta_bucket,
                "beta_adjusted_notional": pos.notional * abs(pos.beta_value),
            }
            for pos in positions
        ]
        
        current_exposure_multiplier = beta_adjusted_notional / user_equity if user_equity > 0 else 0.0
        
        return ExposureSummary(
            user_id=str(user_id),
            total_notional=total_notional,
            beta_adjusted_notional=beta_adjusted_notional,
            position_count=len(positions),
            positions=positions_data,
            current_exposure_multiplier=current_exposure_multiplier,
            limit_exposure_multiplier=limit_multiplier,
        )

    def validate_new_position(
        self,
        user_id: str | UUID,
        user_equity: float,
        new_notional: float,
        new_beta: float = 1.0,
        limit_multiplier: float = 2.0,
    ) -> dict[str, Any]:
        """
        Validate if a new position would exceed exposure limits.
        
        Args:
            user_id: User ID
            user_equity: User's current equity
            new_notional: Notional value of new position
            new_beta: Beta value of new position (default: 1.0)
            limit_multiplier: Maximum allowed exposure multiplier (default: 2.0)
            
        Returns:
            Dict with 'allowed': bool, 'reason': str, 'current_exposure': float, 'projected_exposure': float
        """
        current_summary = self.calculate_exposure_summary(user_id, user_equity, limit_multiplier)
        
        # Calculate projected exposure with new position
        projected_beta_adjusted = current_summary.beta_adjusted_notional + (new_notional * abs(new_beta))
        projected_multiplier = projected_beta_adjusted / user_equity if user_equity > 0 else 0.0
        
        limit_notional = user_equity * limit_multiplier
        
        if projected_multiplier > limit_multiplier:
            return {
                "allowed": False,
                "reason": f"Exposición agregada excedería límite: {projected_multiplier:.2f}× > {limit_multiplier:.2f}×",
                "current_exposure_multiplier": current_summary.current_exposure_multiplier,
                "projected_exposure_multiplier": projected_multiplier,
                "limit_multiplier": limit_multiplier,
                "current_beta_adjusted_notional": current_summary.beta_adjusted_notional,
                "projected_beta_adjusted_notional": projected_beta_adjusted,
                "limit_beta_adjusted_notional": limit_notional,
                "exceeds_by": projected_beta_adjusted - limit_notional,
            }
        
        return {
            "allowed": True,
            "reason": None,
            "current_exposure_multiplier": current_summary.current_exposure_multiplier,
            "projected_exposure_multiplier": projected_multiplier,
            "limit_multiplier": limit_multiplier,
            "current_beta_adjusted_notional": current_summary.beta_adjusted_notional,
            "projected_beta_adjusted_notional": projected_beta_adjusted,
        }

    def calculate_beta(
        self,
        symbol: str,
        market_symbol: str = "BTCUSDT",
    ) -> float:
        """
        Calculate beta for a symbol relative to market (BTCUSDT).
        
        For now, uses simplified approach:
        - BTCUSDT: beta = 1.0 (market benchmark)
        - Other symbols: estimate from correlation (if available) or use default
        
        Args:
            symbol: Trading symbol
            market_symbol: Market benchmark symbol (default: BTCUSDT)
            
        Returns:
            Beta value (default: 1.0 for BTCUSDT, 0.8-1.2 for others)
        """
        # For BTCUSDT, beta is always 1.0 (it's the market)
        if symbol == market_symbol:
            return 1.0
        
        # TODO: Calculate actual beta from historical returns
        # For now, use conservative estimates based on typical crypto correlations
        # Most altcoins have beta 0.8-1.5 vs BTC
        # Using 1.0 as default (high correlation assumption)
        return 1.0

