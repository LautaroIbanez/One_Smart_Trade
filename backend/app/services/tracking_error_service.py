"""Service for monitoring tracking error between proposed SL/TP and actual prices reached."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import logger, sanitize_log_extra
from app.data.curation import DataCuration
from app.db.crud import get_open_recommendation, get_recommendation_history
from app.db.models import RecommendationORM
from app.services.alert_service import AlertService


class TrackingErrorService:
    """Service to monitor and calculate tracking error for recommendations."""
    
    def __init__(self):
        self.curation = DataCuration()
        self.alerts = AlertService()
    
    async def monitor_tracking_errors(self) -> dict[str, Any]:
        """
        Monitor open recommendations and calculate tracking error for closed ones.
        
        Returns:
            Dict with monitoring results and alerts
        """
        db = SessionLocal()
        try:
            # Get open recommendations
            open_rec = get_open_recommendation(db)
            if not open_rec:
                return {"status": "no_open_recommendations", "updated": 0, "alerts": []}
            
            # Get recent closed recommendations (last 7 days) that don't have tracking_error_bps
            cutoff_date = datetime.utcnow() - timedelta(days=settings.TRACKING_ERROR_CHECK_LOOKAHEAD_DAYS)
            recent_recs = db.query(RecommendationORM).filter(
                RecommendationORM.status == "closed",
                RecommendationORM.closed_at >= cutoff_date,
                RecommendationORM.tracking_error_bps.is_(None),
                RecommendationORM.exit_reason.isnot(None),
                RecommendationORM.exit_price.isnot(None),
            ).all()
            
            updated_count = 0
            alerts = []
            
            for rec in recent_recs:
                try:
                    tracking_error_bps = await self._calculate_tracking_error(rec)
                    if tracking_error_bps is not None:
                        rec.tracking_error_bps = tracking_error_bps
                        db.commit()
                        updated_count += 1
                        
                        # Check if tracking error exceeds threshold
                        if tracking_error_bps > settings.TRACKING_ERROR_THRESHOLD_BPS:
                            alert = {
                                "recommendation_id": rec.id,
                                "date": rec.date,
                                "signal": rec.signal,
                                "exit_reason": rec.exit_reason,
                                "tracking_error_bps": tracking_error_bps,
                                "threshold_bps": settings.TRACKING_ERROR_THRESHOLD_BPS,
                                "target_price": rec.take_profit if rec.exit_reason.upper() in ("TP", "TAKE_PROFIT") else rec.stop_loss,
                                "actual_exit_price": rec.exit_price,
                            }
                            alerts.append(alert)
                            
                            logger.warning(
                                f"Tracking error exceeds threshold for recommendation {rec.id}: {tracking_error_bps:.2f} bps > {settings.TRACKING_ERROR_THRESHOLD_BPS} bps",
                                extra=sanitize_log_extra(alert),  # Avoid reserved LogRecord keys.
                            )
                            
                            # Send alert
                            try:
                                await self.alerts.send_alert(
                                    level="warning",
                                    title="Tracking Error Threshold Exceeded",
                                    message=f"Recommendation {rec.id} ({rec.date}) has tracking error of {tracking_error_bps:.2f} bps, exceeding threshold of {settings.TRACKING_ERROR_THRESHOLD_BPS} bps",
                                    metadata=alert,
                                )
                            except Exception as e:
                                logger.warning(f"Failed to send tracking error alert: {e}", exc_info=True)
                except Exception as e:
                    logger.warning(f"Failed to calculate tracking error for recommendation {rec.id}: {e}", exc_info=True)
                    continue
            
            return {
                "status": "success",
                "updated": updated_count,
                "alerts": alerts,
            }
        finally:
            db.close()
    
    async def _calculate_tracking_error(self, rec: RecommendationORM) -> float | None:
        """
        Calculate tracking error for a closed recommendation.
        
        Tracking error is the difference between the target price (SL or TP) and
        the actual price reached, expressed in basis points.
        
        Args:
            rec: Recommendation with exit_price and exit_reason
        
        Returns:
            Tracking error in basis points, or None if cannot be calculated
        """
        if not rec.exit_price or not rec.exit_reason:
            return None
        
        # Determine target price based on exit reason
        target_price = None
        if rec.exit_reason.upper() in ("TP", "TAKE_PROFIT", "take_profit"):
            target_price = rec.take_profit
        elif rec.exit_reason.upper() in ("SL", "STOP_LOSS", "stop_loss"):
            target_price = rec.stop_loss
        else:
            # For other exit reasons, check if TP or SL was actually hit
            target_price = await self._check_if_sl_tp_was_hit(rec)
        
        if not target_price or target_price <= 0:
            return None
        
        # Calculate tracking error as percentage difference
        tracking_error_pct = abs((rec.exit_price - target_price) / target_price) * 100.0
        tracking_error_bps = tracking_error_pct * 100.0  # Convert to basis points
        
        return round(tracking_error_bps, 2)
    
    async def _check_if_sl_tp_was_hit(self, rec: RecommendationORM) -> float | None:
        """
        Check historical prices to determine if SL or TP was actually hit.
        
        This is used when exit_reason is not explicitly TP or SL, but we want
        to verify if the proposed levels were achievable.
        
        Args:
            rec: Recommendation to check
        
        Returns:
            Target price (SL or TP) if it was hit, None otherwise
        """
        try:
            # Get historical prices from recommendation date
            rec_date = datetime.strptime(rec.date, "%Y-%m-%d").date()
            df = self.curation.get_historical_curated("1h", days=settings.TRACKING_ERROR_CHECK_LOOKAHEAD_DAYS)
            
            if df is None or df.empty:
                return None
            
            # Filter to dates after recommendation
            if "open_time" in df.columns:
                df["date"] = pd.to_datetime(df["open_time"]).dt.date
                df = df[df["date"] >= rec_date]
            
            if df.empty:
                return None
            
            # Check if SL or TP was hit
            if rec.signal == "BUY":
                # For BUY: check if low hit SL or high hit TP
                min_low = float(df["low"].min())
                max_high = float(df["high"].max())
                
                if min_low <= rec.stop_loss:
                    return rec.stop_loss
                elif max_high >= rec.take_profit:
                    return rec.take_profit
            elif rec.signal == "SELL":
                # For SELL: check if high hit SL or low hit TP
                max_high = float(df["high"].max())
                min_low = float(df["low"].min())
                
                if max_high >= rec.stop_loss:
                    return rec.stop_loss
                elif min_low <= rec.take_profit:
                    return rec.take_profit
            
            return None
        except Exception as e:
            logger.warning(f"Failed to check SL/TP achievability for recommendation {rec.id}: {e}", exc_info=True)
            return None
    
    async def update_tracking_error_for_recommendation(self, rec_id: int) -> dict[str, Any]:
        """
        Update tracking error for a specific recommendation.
        
        Args:
            rec_id: Recommendation ID
        
        Returns:
            Dict with update result
        """
        db = SessionLocal()
        try:
            rec = db.query(RecommendationORM).filter(RecommendationORM.id == rec_id).first()
            if not rec:
                return {"status": "not_found", "recommendation_id": rec_id}
            
            if rec.status != "closed" or not rec.exit_price or not rec.exit_reason:
                return {"status": "not_applicable", "reason": "Recommendation not closed or missing exit data"}
            
            tracking_error_bps = await self._calculate_tracking_error(rec)
            if tracking_error_bps is not None:
                rec.tracking_error_bps = tracking_error_bps
                db.commit()
                
                # Check threshold
                alert_sent = False
                if tracking_error_bps > settings.TRACKING_ERROR_THRESHOLD_BPS:
                    try:
                        await self.alerts.send_alert(
                            level="warning",
                            title="Tracking Error Threshold Exceeded",
                            message=f"Recommendation {rec.id} has tracking error of {tracking_error_bps:.2f} bps",
                            metadata={
                                "recommendation_id": rec.id,
                                "tracking_error_bps": tracking_error_bps,
                                "threshold_bps": settings.TRACKING_ERROR_THRESHOLD_BPS,
                            },
                        )
                        alert_sent = True
                    except Exception as e:
                        logger.warning(f"Failed to send alert: {e}", exc_info=True)
                
                return {
                    "status": "updated",
                    "recommendation_id": rec_id,
                    "tracking_error_bps": tracking_error_bps,
                    "alert_sent": alert_sent,
                }
            else:
                return {"status": "cannot_calculate", "recommendation_id": rec_id}
        finally:
            db.close()

