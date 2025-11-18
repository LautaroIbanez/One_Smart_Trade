"""User risk profile service for comprehensive risk context management."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.core.database import SessionLocal
from app.core.logging import logger
from app.db.crud import get_user_risk_state, get_open_recommendation
from app.db.models import UserRiskStateORM, RecommendationORM


@dataclass
class UserRiskContext:
    """Comprehensive user risk context for position sizing and risk management."""

    user_id: str
    equity: float
    drawdown_pct: float
    base_risk_pct: float
    realized_vol: float | None
    avg_exposure_pct: float
    total_notional: float
    effective_leverage: float
    open_positions_count: int
    has_data: bool
    max_drawdown_pct: float | None = None
    peak_equity: float | None = None
    win_rate: float | None = None
    payoff_ratio: float | None = None
    trade_history: list[dict[str, Any]] | None = None

    @property
    def exposure_available(self) -> float:
        """Calculate available exposure capacity (1.0 = 100% of equity)."""
        if self.equity <= 0:
            return 0.0
        # Available exposure = 1.0 - current exposure
        current_exposure = self.total_notional / self.equity if self.equity > 0 else 0.0
        return max(0.0, 1.0 - current_exposure)

    @property
    def is_overexposed(self) -> bool:
        """Check if user is overexposed (leverage > 2.0 or exposure > 100%)."""
        return self.effective_leverage > 2.0 or (self.total_notional / self.equity if self.equity > 0 else 0.0) > 1.0

    @property
    def risk_capacity(self) -> float:
        """Calculate risk capacity multiplier (0.0 to 1.0) based on drawdown and exposure."""
        if not self.has_data or self.equity <= 0:
            return 0.0
        
        # Drawdown penalty: reduce capacity as drawdown increases
        dd_penalty = max(0.2, 1.0 - (self.drawdown_pct / 50.0))  # At 50% DD, capacity = 0.2
        
        # Exposure penalty: reduce capacity as exposure increases
        exposure_ratio = self.total_notional / self.equity if self.equity > 0 else 0.0
        exposure_penalty = max(0.3, 1.0 - (exposure_ratio * 0.5))  # At 100% exposure, capacity = 0.5
        
        return min(1.0, dd_penalty * exposure_penalty)


class UserRiskProfileService:
    """Service for retrieving comprehensive user risk profile and context."""

    def __init__(self, session=None):
        """Initialize service."""
        self.session = session

    def get_context(
        self,
        user_id: str | UUID | None,
        *,
        realized_vol: float | None = None,
        base_risk_pct: float = 1.0,
    ) -> UserRiskContext:
        """
        Get comprehensive user risk context for position sizing.

        Args:
            user_id: User ID (if None, returns empty context)
            realized_vol: Optional realized volatility estimate (annualized, e.g., 0.15 for 15%)
            base_risk_pct: Base risk percentage (default: 1.0%)

        Returns:
            UserRiskContext with all risk metrics
        """
        if user_id is None:
            logger.debug("No user_id provided, returning empty context")
            return UserRiskContext(
                user_id="default",
                equity=0.0,
                drawdown_pct=0.0,
                base_risk_pct=base_risk_pct,
                realized_vol=realized_vol,
                avg_exposure_pct=0.0,
                total_notional=0.0,
                effective_leverage=0.0,
                open_positions_count=0,
                has_data=False,
                win_rate=None,
                payoff_ratio=None,
                trade_history=None,
            )

        try:
            user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
        except (ValueError, TypeError):
            logger.warning(f"Invalid user_id format: {user_id}, returning empty context")
            return UserRiskContext(
                user_id=str(user_id),
                equity=0.0,
                drawdown_pct=0.0,
                base_risk_pct=base_risk_pct,
                realized_vol=realized_vol,
                avg_exposure_pct=0.0,
                total_notional=0.0,
                effective_leverage=0.0,
                open_positions_count=0,
                has_data=False,
            )

        db = self.session or SessionLocal()
        try:
            risk_state = get_user_risk_state(db, user_uuid)
            
            # Count open positions (recommendations with status="open")
            open_rec = get_open_recommendation(db)
            open_positions_count = 1 if open_rec else 0
            
            # Calculate peak equity if we have drawdown
            peak_equity = None
            max_drawdown_pct = None
            if risk_state and risk_state.current_equity and risk_state.current_equity > 0:
                if risk_state.current_drawdown_pct and risk_state.current_drawdown_pct > 0:
                    # Peak = current / (1 - drawdown_pct/100)
                    peak_equity = risk_state.current_equity / (1.0 - (risk_state.current_drawdown_pct / 100.0))
                    max_drawdown_pct = risk_state.current_drawdown_pct
            
            if risk_state is None or risk_state.current_equity is None or risk_state.current_equity <= 0:
                logger.info(f"User {user_id} has no equity data, returning empty context")
                return UserRiskContext(
                    user_id=str(user_id),
                    equity=0.0,
                    drawdown_pct=0.0,
                    base_risk_pct=base_risk_pct,
                    realized_vol=realized_vol,
                    avg_exposure_pct=0.0,
                    total_notional=0.0,
                    effective_leverage=0.0,
                    open_positions_count=open_positions_count,
                    has_data=False,
                )
            
            # Calculate win_rate, payoff_ratio, and trade_history from closed trades
            win_rate, payoff_ratio, trade_history = self._calculate_trading_metrics(db, user_uuid)
            
            context = UserRiskContext(
                user_id=str(user_id),
                equity=risk_state.current_equity or 0.0,
                drawdown_pct=risk_state.current_drawdown_pct or 0.0,
                base_risk_pct=base_risk_pct,
                realized_vol=realized_vol,
                avg_exposure_pct=risk_state.avg_exposure_pct or 0.0,
                total_notional=risk_state.total_notional or 0.0,
                effective_leverage=risk_state.effective_leverage or 0.0,
                open_positions_count=open_positions_count,
                has_data=True,
                max_drawdown_pct=max_drawdown_pct,
                peak_equity=peak_equity,
                win_rate=win_rate,
                payoff_ratio=payoff_ratio,
                trade_history=trade_history,
            )
            
            logger.debug(
                f"User {user_id} risk context: equity=${context.equity:,.2f}, "
                f"DD={context.drawdown_pct:.2f}%, exposure={context.avg_exposure_pct:.2f}%, "
                f"leverage={context.effective_leverage:.2f}x, risk_capacity={context.risk_capacity:.2f}"
            )
            
            return context
        except Exception as e:
            logger.warning(f"Error fetching user risk context for {user_id}: {e}", exc_info=True)
            return UserRiskContext(
                user_id=str(user_id),
                equity=0.0,
                drawdown_pct=0.0,
                base_risk_pct=base_risk_pct,
                realized_vol=realized_vol,
                avg_exposure_pct=0.0,
                total_notional=0.0,
                effective_leverage=0.0,
                open_positions_count=0,
                has_data=False,
            )
        finally:
            if not self.session:
                db.close()

    def _calculate_trading_metrics(
        self,
        db,
        user_id: UUID,
        limit: int = 100,
    ) -> tuple[float | None, float | None, list[dict[str, Any]]]:
        """
        Calculate win_rate, payoff_ratio, and trade_history from closed trades.
        
        Args:
            db: Database session
            user_id: User UUID
            limit: Maximum number of trades to analyze (default: 100)
            
        Returns:
            Tuple of (win_rate, payoff_ratio, trade_history)
        """
        try:
            from sqlalchemy import select
            from app.db.models import RecommendationORM
            
            # Get closed trades (for now, all trades since no user_id in recommendations)
            # In multi-user system, filter by user_id
            stmt = (
                select(RecommendationORM)
                .where(RecommendationORM.status == "closed")
                .where(RecommendationORM.exit_price.isnot(None))
                .where(RecommendationORM.entry_optimal.isnot(None))
                .order_by(RecommendationORM.closed_at.desc())
                .limit(limit)
            )
            closed_recs = list(db.execute(stmt).scalars().all())
            
            if not closed_recs:
                return None, None, []
            
            # Build trade history
            trades = []
            wins = []
            losses = []
            
            for rec in closed_recs:
                entry = rec.entry_optimal
                exit_price = rec.exit_price
                
                # Calculate return percentage
                if rec.signal == "BUY":
                    return_pct = ((exit_price - entry) / entry) * 100
                elif rec.signal == "SELL":
                    return_pct = ((entry - exit_price) / entry) * 100
                else:
                    return_pct = 0.0
                
                trades.append({
                    "pnl": return_pct,
                    "return_pct": return_pct,
                    "entry_price": entry,
                    "exit_price": exit_price,
                    "side": rec.signal,
                })
                
                if return_pct > 0:
                    wins.append(return_pct)
                elif return_pct < 0:
                    losses.append(abs(return_pct))
            
            # Calculate win_rate
            win_rate = len(wins) / len(trades) if trades else None
            
            # Calculate payoff_ratio (avg_win / avg_loss)
            payoff_ratio = None
            if wins and losses:
                avg_win = sum(wins) / len(wins)
                avg_loss = sum(losses) / len(losses)
                if avg_loss > 0:
                    payoff_ratio = avg_win / avg_loss
            elif wins and not losses:
                # All wins, use conservative estimate
                payoff_ratio = 1.0
            elif losses and not wins:
                # All losses, use conservative estimate
                payoff_ratio = 0.5
            
            return win_rate, payoff_ratio, trades
            
        except Exception as e:
            logger.warning(f"Error calculating trading metrics: {e}", exc_info=True)
            return None, None, []

    def get_open_positions(self, user_id: str | UUID | None) -> list[dict[str, Any]]:
        """
        Get open positions with real notional values.
        
        Args:
            user_id: User ID (optional, for future multi-user support)
            
        Returns:
            List of position dicts with 'symbol', 'notional', 'side', 'entry' keys
        """
        db = self.session or SessionLocal()
        try:
            from app.db.crud import get_open_recommendation
            from sqlalchemy import select
            from app.db.models import RecommendationORM
            
            # Get all open recommendations (positions)
            stmt = (
                select(RecommendationORM)
                .where(RecommendationORM.status == "open")
                .where(RecommendationORM.entry_optimal.isnot(None))
            )
            open_recs = list(db.execute(stmt).scalars().all())
            
            positions = []
            for rec in open_recs:
                # Calculate notional: entry_price * position_size
                # Position size is stored in recommended_position_size or we estimate from risk
                entry = rec.entry_optimal
                symbol = "BTCUSDT"  # Default, could be stored in future
                
                # Try to get actual position size from risk_metrics or estimate
                notional = 0.0
                risk_metrics = rec.risk_metrics or {}
                if "suggested_sizing" in risk_metrics:
                    sizing = risk_metrics["suggested_sizing"]
                    notional = sizing.get("notional", 0.0)
                elif "recommended_position_size" in risk_metrics:
                    units = risk_metrics.get("recommended_position_size", 0.0)
                    notional = units * entry if entry > 0 else 0.0
                else:
                    # Estimate: assume 1% risk of equity (conservative)
                    # This is a fallback - in production, position size should be tracked
                    notional = entry * 0.01  # Very rough estimate
                
                positions.append({
                    "symbol": symbol,
                    "notional": notional,
                    "side": rec.signal,  # BUY or SELL
                    "entry": entry,
                    "recommendation_id": rec.id,
                })
            
            return positions
        except Exception as e:
            logger.warning(f"Error fetching open positions: {e}", exc_info=True)
            return []
        finally:
            if not self.session:
                db.close()

