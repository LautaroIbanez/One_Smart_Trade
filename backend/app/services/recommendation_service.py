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
        """Get today's recommendation."""
        today = datetime.utcnow().date()
        if self._cache and self._cache_timestamp and self._cache_timestamp.date() == today:
            return self._cache

        # Try DB first
        with SessionLocal() as db:
            rec = get_latest_recommendation(db)
            if rec and self._cache_timestamp and self._cache_timestamp.date() == today:
                return self._from_orm(rec)

        # Generate on-demand if not present
        dc = DataCuration()
        df_1d = dc.get_latest_curated("1d")
        df_1h = dc.get_latest_curated("1h") or df_1d
        if df_1d is None or df_1d.empty:
            return None
        recommendation = generate_signal(df_1h, df_1d)
        with SessionLocal() as db:
            create_recommendation(db, recommendation)
        if recommendation:
            self._cache = recommendation
            self._cache_timestamp = datetime.utcnow()
        return recommendation

    async def get_recommendation_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recommendation history."""
        with SessionLocal() as db:
            recs = db_history(db, limit=limit)
            return [self._from_orm(r) for r in recs]

    def _from_orm(self, r) -> Dict[str, Any]:
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
            "analysis": "",
            "indicators": r.indicators,
            "risk_metrics": r.risk_metrics,
            "timestamp": r.created_at.isoformat(),
            "disclaimer": "This is not financial advice. Trading cryptocurrencies involves significant risk.",
        }

