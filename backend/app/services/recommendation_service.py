"""Recommendation service."""
from datetime import datetime
from typing import Any, Optional

from app.core.database import SessionLocal
from app.core.logging import logger
from app.data.curation import DataCuration
from app.db.crud import create_recommendation, get_latest_recommendation
from app.db.crud import get_recommendation_history as db_history
from app.quant.signal_engine import generate_signal


class RecommendationService:
    """Service for managing trading recommendations."""

    def __init__(self, session=None):
        self._cache: Optional[dict[str, Any]] = None
        self._cache_timestamp: Optional[datetime] = None
        self.session = session
        self.curation = DataCuration()

    async def generate_recommendation(self) -> Optional[dict[str, Any]]:
        """Generate a new recommendation using curated datasets."""
        from app.quant.narrative import build_narrative

        try:
            latest_daily = self.curation.get_latest_curated("1d")
        except FileNotFoundError:
            logger.warning("Cannot generate recommendation: no 1d curated data available")
            return None

        try:
            latest_hourly = self.curation.get_latest_curated("1h")
        except FileNotFoundError:
            logger.warning("No 1h data available, using 1d as fallback")
            latest_hourly = latest_daily

        if latest_daily is None or latest_daily.empty:
            logger.warning("Cannot generate recommendation: no 1d curated data available")
            return None

        if latest_hourly is None or latest_hourly.empty:
            logger.warning("1h dataset empty, using 1d as fallback")
            latest_hourly = latest_daily

        signal = generate_signal(latest_hourly, latest_daily)
        analysis = build_narrative(signal)
        signal["analysis"] = analysis

        rec = None

        # Save recommendation if session is provided
        if self.session:
            rec = create_recommendation(self.session, signal)
        else:
            # Fallback to creating a new session
            with SessionLocal() as db:
                try:
                    rec = create_recommendation(db, signal)
                finally:
                    db.close()

        logger.info(f"Generated and saved recommendation: {signal['signal']}")
        return self._from_orm(rec) if rec else signal

    async def get_today_recommendation(self) -> Optional[dict[str, Any]]:
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
        try:
            df_1d = dc.get_latest_curated("1d")
        except FileNotFoundError:
            logger.warning("Cannot generate recommendation: no 1d curated data available")
            return None

        try:
            df_1h = dc.get_latest_curated("1h")
        except FileNotFoundError:
            logger.warning("No 1h data available, using 1d as fallback")
            df_1h = df_1d

        if df_1d is None or df_1d.empty:
            logger.warning("Cannot generate recommendation: no 1d curated data available")
            return None

        if df_1h is None or df_1h.empty:
            logger.warning("1h dataset empty, using 1d as fallback")
            df_1h = df_1d

        try:
            recommendation = generate_signal(df_1h, df_1d)
            # Add analysis if not present (will be generated in create_recommendation)
            if "analysis" not in recommendation or not recommendation["analysis"]:
                from app.quant.narrative import build_narrative
                recommendation["analysis"] = build_narrative(recommendation)

            result = None
            with SessionLocal() as db:
                try:
                    rec = create_recommendation(db, recommendation)
                    logger.info(f"Generated and saved recommendation: {recommendation['signal']}")
                    result = self._from_orm(rec)
                finally:
                    db.close()

            if result:
                self._cache = result
                self._cache_timestamp = datetime.utcnow()
            return result
        except Exception as e:
            logger.error(f"Error generating recommendation: {e}", exc_info=True)
            return None

    async def get_recommendation_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recommendation history from DB."""
        with SessionLocal() as db:
            try:
                recs = db_history(db, limit=limit)
                return [self._from_orm(r) for r in recs]
            finally:
                db.close()

    def _from_orm(self, r) -> dict[str, Any]:
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

