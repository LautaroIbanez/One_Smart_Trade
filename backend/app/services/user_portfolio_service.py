"""User portfolio service for retrieving user-specific risk and equity data."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.core.database import SessionLocal
from app.core.logging import logger
from app.db.crud import get_user_risk_state
from app.db.models import UserRiskStateORM


@dataclass
class UserPortfolioData:
    """User portfolio data for risk management."""

    user_id: str
    current_equity: float
    current_drawdown_pct: float
    volatility_estimate: float | None
    has_data: bool

    @classmethod
    def from_risk_state(cls, user_id: str, risk_state: UserRiskStateORM | None, volatility_estimate: float | None = None) -> UserPortfolioData:
        """Create from UserRiskStateORM."""
        if risk_state is None:
            return cls(
                user_id=user_id,
                current_equity=0.0,
                current_drawdown_pct=0.0,
                volatility_estimate=volatility_estimate,
                has_data=False,
            )
        return cls(
            user_id=user_id,
            current_equity=risk_state.current_equity or 0.0,
            current_drawdown_pct=risk_state.current_drawdown_pct or 0.0,
            volatility_estimate=volatility_estimate,
            has_data=risk_state.current_equity is not None and risk_state.current_equity > 0.0,
        )


class UserPortfolioService:
    """Service for retrieving user portfolio and risk data."""

    def __init__(self, session=None):
        """Initialize service."""
        self.session = session

    def get_user_portfolio(
        self,
        user_id: str | UUID | None,
        *,
        volatility_estimate: float | None = None,
    ) -> UserPortfolioData:
        """
        Get user portfolio data for risk management.

        Args:
            user_id: User ID (if None, returns default conservative profile)
            volatility_estimate: Optional volatility estimate (annualized, e.g., 0.15 for 15%)

        Returns:
            UserPortfolioData with equity, drawdown, and volatility
        """
        if user_id is None:
            logger.debug("No user_id provided, returning default conservative profile")
            return UserPortfolioData(
                user_id="default",
                current_equity=0.0,
                current_drawdown_pct=0.0,
                volatility_estimate=volatility_estimate,
                has_data=False,
            )

        try:
            user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
        except (ValueError, TypeError):
            logger.warning(f"Invalid user_id format: {user_id}, returning default profile")
            return UserPortfolioData(
                user_id=str(user_id),
                current_equity=0.0,
                current_drawdown_pct=0.0,
                volatility_estimate=volatility_estimate,
                has_data=False,
            )

        db = self.session or SessionLocal()
        try:
            risk_state = get_user_risk_state(db, user_uuid)
            portfolio = UserPortfolioData.from_risk_state(str(user_id), risk_state, volatility_estimate)
            
            if not portfolio.has_data:
                logger.info(f"User {user_id} has no portfolio data, using conservative profile")
            
            return portfolio
        except Exception as e:
            logger.warning(f"Error fetching user portfolio for {user_id}: {e}", exc_info=True)
            return UserPortfolioData(
                user_id=str(user_id),
                current_equity=0.0,
                current_drawdown_pct=0.0,
                volatility_estimate=volatility_estimate,
                has_data=False,
            )
        finally:
            if not self.session:
                db.close()

