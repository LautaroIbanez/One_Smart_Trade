"""Service for monitoring exposure alerts and triggering notifications."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from app.core.database import SessionLocal
from app.core.logging import logger
from app.core.config import settings
from app.services.exposure_ledger_service import ExposureLedgerService
from app.services.user_risk_profile_service import UserRiskProfileService
from app.services.alert_service import AlertService


class ExposureAlertService:
    """Service for monitoring exposure levels and triggering alerts."""

    def __init__(self, session=None):
        """Initialize service."""
        self.session = session
        self.exposure_ledger_service = ExposureLedgerService(session=session)
        self.user_risk_service = UserRiskProfileService(session=session)
        self.alert_service = AlertService()
        self.alert_threshold_pct = 0.8  # 80% of limit
        self.alert_persistence_minutes = 15  # Must persist for 15 minutes

    def check_exposure_alerts(
        self,
        user_id: str | UUID,
        *,
        alert_threshold_pct: float = 0.8,
        persistence_minutes: int = 15,
    ) -> dict[str, Any]:
        """
        Check if user exposure exceeds alert threshold and has persisted.
        
        Args:
            user_id: User ID
            alert_threshold_pct: Alert threshold as percentage of limit (default: 0.8 = 80%)
            persistence_minutes: Minutes exposure must exceed threshold to trigger alert (default: 15)
            
        Returns:
            Dict with alert status and details
        """
        try:
            user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
        except (ValueError, TypeError):
            return {"alert_active": False, "error": "Invalid user_id format"}

        db = self.session or SessionLocal()
        try:
            # Get user context
            ctx = self.user_risk_service.get_context(user_id, base_risk_pct=1.0)
            
            if not ctx.has_data or ctx.equity <= 0:
                return {"alert_active": False, "reason": "no_equity_data"}
            
            # Get exposure summary
            exposure_summary = self.exposure_ledger_service.calculate_exposure_summary(
                user_id=user_id,
                user_equity=ctx.equity,
                limit_multiplier=settings.EXPOSURE_LIMIT_MULTIPLIER,
            )
            
            # Calculate utilization percentage
            utilization_pct = (
                exposure_summary.current_exposure_multiplier / exposure_summary.limit_exposure_multiplier
                if exposure_summary.limit_exposure_multiplier > 0 else 0.0
            )
            
            # Check if exceeds threshold
            exceeds_threshold = utilization_pct > alert_threshold_pct
            
            if not exceeds_threshold:
                return {
                    "alert_active": False,
                    "utilization_pct": utilization_pct * 100.0,
                    "threshold_pct": alert_threshold_pct * 100.0,
                    "current_exposure_multiplier": exposure_summary.current_exposure_multiplier,
                    "limit_multiplier": exposure_summary.limit_exposure_multiplier,
                }
            
            # Check persistence (simplified: for now, just check current state)
            # TODO: Implement time-based persistence tracking in database
            # For now, we'll trigger alert immediately if threshold exceeded
            
            alert_message = (
                f"Usuario {user_id}: Exposición alta detectada. "
                f"Utilización: {utilization_pct:.1%} ({exposure_summary.current_exposure_multiplier:.2f}× / "
                f"límite {exposure_summary.limit_exposure_multiplier:.2f}×). "
                f"Posiciones activas: {exposure_summary.position_count}."
            )
            
            # Trigger alert
            self.alert_service.notify(
                "risk_monitor.high_exposure",
                alert_message,
                payload={
                    "user_id": str(user_id),
                    "utilization_pct": utilization_pct * 100.0,
                    "current_exposure_multiplier": exposure_summary.current_exposure_multiplier,
                    "limit_multiplier": exposure_summary.limit_exposure_multiplier,
                    "position_count": exposure_summary.position_count,
                    "beta_adjusted_notional": exposure_summary.beta_adjusted_notional,
                    "equity": ctx.equity,
                },
            )
            
            logger.warning(
                f"Exposure alert triggered for user {user_id}: {utilization_pct:.1%} utilization",
                extra={
                    "user_id": str(user_id),
                    "utilization_pct": utilization_pct,
                    "current_exposure": exposure_summary.current_exposure_multiplier,
                    "limit": exposure_summary.limit_exposure_multiplier,
                }
            )
            
            return {
                "alert_active": True,
                "utilization_pct": utilization_pct * 100.0,
                "threshold_pct": alert_threshold_pct * 100.0,
                "current_exposure_multiplier": exposure_summary.current_exposure_multiplier,
                "limit_multiplier": exposure_summary.limit_exposure_multiplier,
                "position_count": exposure_summary.position_count,
                "message": alert_message,
            }
        except Exception as e:
            logger.error(f"Error checking exposure alerts for user {user_id}: {e}", exc_info=True)
            return {"alert_active": False, "error": str(e)}
        finally:
            if not self.session:
                db.close()

