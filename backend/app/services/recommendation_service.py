"""Recommendation service."""
from typing import Optional, List, Dict, Any
from datetime import datetime
from app.quant.signal_engine import generate_signal
from app.core.logging import logger
from app.data.curation import DataCuration
from app.core.database import SessionLocal
from app.db.crud import get_latest_recommendation, get_recommendation_history as db_history, create_recommendation


class RecommendationService:
    """Service for managing trading recommendations."""

    def __init__(self):
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_timestamp: Optional[datetime] = None

    async def get_today_recommendation(self) -> Optional[Dict[str, Any]]:
        """Get today's recommendation from DB or generate on-demand."""
        today = datetime.utcnow().date()
        
        # Check cache first
        if self._cache and self._cache_timestamp and self._cache_timestamp.date() == today:
            logger.debug("Returning cached recommendation")
            return self._cache

        # Try DB first
        with SessionLocal() as db:
            try:
                rec = get_latest_recommendation(db)
                if rec:
                    rec_date = rec.created_at.date()
                    if rec_date == today:
                        logger.info(f"Found today's recommendation in DB (created at {rec.created_at})")
                        result = self._from_orm(rec)
                        self._cache = result
                        self._cache_timestamp = rec.created_at
                        return result
                    else:
                        logger.debug(f"Latest recommendation is from {rec_date}, not today")
            finally:
                db.close()

        # Generate on-demand if not present
        logger.info("Generating recommendation on-demand")
        dc = DataCuration()
        df_1d = dc.get_latest_curated("1d")
        df_1h = dc.get_latest_curated("1h")
        
        if df_1d is None or df_1d.empty:
            logger.warning("Cannot generate recommendation: no 1d curated data available")
            return None
        
        if df_1h is None or df_1h.empty:
            logger.warning("No 1h data available, using 1d as fallback")
            df_1h = df_1d
        
        try:
            recommendation = generate_signal(df_1h, df_1d)
            # Add analysis if not present (will be generated in create_recommendation)
            if "analysis" not in recommendation or not recommendation["analysis"]:
                from app.quant.narrative import build_narrative
                recommendation["analysis"] = build_narrative(recommendation)
            
            with SessionLocal() as db:
                try:
                    create_recommendation(db, recommendation)
                    logger.info(f"Generated and saved recommendation: {recommendation['signal']}")
                finally:
                    db.close()
            
            if recommendation:
                self._cache = recommendation
                self._cache_timestamp = datetime.utcnow()
            return recommendation
        except Exception as e:
            logger.error(f"Error generating recommendation: {e}", exc_info=True)
            return None

    async def get_recommendation_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recommendation history from DB."""
        with SessionLocal() as db:
            try:
                recs = db_history(db, limit=limit)
                return [self._from_orm(r) for r in recs]
            finally:
                db.close()

    def _from_orm(self, r) -> Dict[str, Any]:
        """Convert ORM model to API response dict."""
        return {
            "signal": r.signal,
            "entry_range": {"min": r.entry_min, "max": r.entry_max, "optimal": r.entry_optimal},
            "stop_loss_take_profit": {
                "stop_loss": r.stop_loss,
                "take_profit": r.take_profit,
                "stop_loss_pct": r.stop_loss_pct,
                "take_profit_pct": r.take_profit_pct,
            },
            "confidence": r.confidence,
            "current_price": r.current_price,
            "analysis": r.analysis or "",
            "indicators": r.indicators or {},
            "risk_metrics": r.risk_metrics or {},
            "factors": r.factors or {},
            "timestamp": r.created_at.isoformat(),
            "disclaimer": "This is not financial advice. Trading cryptocurrencies involves significant risk.",
        }

