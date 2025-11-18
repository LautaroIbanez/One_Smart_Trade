"""Risk reporting service for generating daily risk reports per user."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from app.core.database import SessionLocal
from app.core.logging import logger
from app.services.user_risk_profile_service import UserRiskProfileService
from app.services.exposure_ledger_service import ExposureLedgerService
from app.db.crud import get_user_risk_state
from app.core.config import settings


class RiskReportingService:
    """Service for generating risk reports and metrics for users."""

    def __init__(self, session=None):
        """Initialize service."""
        self.session = session
        self.user_risk_service = UserRiskProfileService(session=session)
        self.exposure_ledger_service = ExposureLedgerService(session=session)
        self.reports_dir = Path("reports/risk")
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def generate_user_risk_report(
        self,
        user_id: str | UUID,
        *,
        include_history: bool = True,
    ) -> dict[str, Any]:
        """
        Generate comprehensive risk report for a user.
        
        Args:
            user_id: User ID
            include_history: Whether to include rejection history (default: True)
            
        Returns:
            Dict with risk metrics and statistics
        """
        try:
            user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
        except (ValueError, TypeError):
            logger.warning(f"Invalid user_id format: {user_id}")
            return {"error": "Invalid user_id format"}

        db = self.session or SessionLocal()
        try:
            # Get user risk context
            ctx = self.user_risk_service.get_context(user_id, base_risk_pct=1.0)
            
            # Get exposure summary
            exposure_summary = self.exposure_ledger_service.calculate_exposure_summary(
                user_id=user_id,
                user_equity=ctx.equity,
                limit_multiplier=settings.EXPOSURE_LIMIT_MULTIPLIER,
            )
            
            # Calculate maximum allowed position size (1% risk of equity)
            max_allowed_size = ctx.equity * 0.01 if ctx.equity > 0 else 0.0
            
            # Count rejections from recent recommendations (last 30 days)
            rejection_count = 0
            rejection_breakdown = {}
            if include_history:
                from datetime import timedelta
                from app.db.crud import get_recommendation_history as db_get_history
                cutoff_date = datetime.utcnow() - timedelta(days=30)
                
                history = db_get_history(db, limit=100)
                for rec in history:
                    if rec.created_at < cutoff_date:
                        continue
                    
                    # Check risk_metrics for rejection status
                    risk_metrics = rec.risk_metrics or {}
                    suggested_sizing = risk_metrics.get("suggested_sizing") or {}
                    status = suggested_sizing.get("status")
                    
                    if status in ("missing_equity", "ruin_risk_too_high", "risk_blocked", "exposure_limit_exceeded"):
                        rejection_count += 1
                        rejection_breakdown[status] = rejection_breakdown.get(status, 0) + 1
            
            # Build report
            report = {
                "user_id": str(user_id),
                "report_date": datetime.utcnow().isoformat(),
                "equity": ctx.equity,
                "drawdown_pct": ctx.drawdown_pct,
                "risk_of_ruin": None,  # Will be calculated if win_rate/payoff_ratio available
                "max_allowed_position_size": max_allowed_size,
                "rejection_count_30d": rejection_count,
                "rejection_breakdown": rejection_breakdown,
                "exposure_metrics": {
                    "current_exposure_multiplier": exposure_summary.current_exposure_multiplier,
                    "limit_exposure_multiplier": exposure_summary.limit_exposure_multiplier,
                    "total_notional": exposure_summary.total_notional,
                    "beta_adjusted_notional": exposure_summary.beta_adjusted_notional,
                    "position_count": exposure_summary.position_count,
                    "exposure_utilization_pct": (
                        (exposure_summary.current_exposure_multiplier / exposure_summary.limit_exposure_multiplier * 100.0)
                        if exposure_summary.limit_exposure_multiplier > 0 else 0.0
                    ),
                },
                "trading_metrics": {
                    "win_rate": ctx.win_rate,
                    "payoff_ratio": ctx.payoff_ratio,
                    "current_drawdown_pct": ctx.drawdown_pct,
                    "effective_leverage": ctx.effective_leverage,
                    "avg_exposure_pct": ctx.avg_exposure_pct,
                },
            }
            
            # Calculate risk of ruin if metrics available
            if ctx.win_rate is not None and ctx.payoff_ratio is not None:
                from app.backtesting.risk import RuinSimulator
                ruin_sim = RuinSimulator()
                risk_of_ruin = ruin_sim.estimate(
                    win_rate=ctx.win_rate,
                    payoff_ratio=ctx.payoff_ratio,
                    horizon=250,
                    threshold=0.5,
                )
                report["risk_of_ruin"] = risk_of_ruin
            
            return report
        except Exception as e:
            logger.error(f"Error generating risk report for user {user_id}: {e}", exc_info=True)
            return {"error": str(e)}
        finally:
            if not self.session:
                db.close()

    def save_user_risk_report(
        self,
        user_id: str | UUID,
        report: dict[str, Any] | None = None,
    ) -> Path:
        """
        Save user risk report to JSON file.
        
        Args:
            user_id: User ID
            report: Optional pre-generated report (if None, generates new)
            
        Returns:
            Path to saved report file
        """
        if report is None:
            report = self.generate_user_risk_report(user_id)
        
        user_id_str = str(user_id)
        filename = f"user_{user_id_str}_risk.json"
        filepath = self.reports_dir / filename
        
        try:
            with open(filepath, "w") as f:
                json.dump(report, f, indent=2, default=str)
            
            logger.info(f"Saved risk report for user {user_id} to {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Failed to save risk report for user {user_id}: {e}", exc_info=True)
            raise

    def generate_all_user_reports(self) -> list[dict[str, Any]]:
        """
        Generate risk reports for all users.
        
        Returns:
            List of report dicts
        """
        # For now, single-user system - generate for default user
        from app.core.config import settings
        
        user_id = settings.DEFAULT_USER_ID
        report = self.generate_user_risk_report(user_id)
        filepath = self.save_user_risk_report(user_id, report)
        
        return [{"user_id": user_id, "report": report, "filepath": str(filepath)}]

