"""Recommendation service."""
from typing import Optional, List, Dict, Any
from datetime import datetime
from app.services.recommendation_engine import RecommendationEngine
from app.core.logging import logger


class RecommendationService:
    """Service for managing trading recommendations."""

    def __init__(self):
        self.engine = RecommendationEngine()
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_timestamp: Optional[datetime] = None

    async def get_today_recommendation(self) -> Optional[Dict[str, Any]]:
        """Get today's recommendation."""
        today = datetime.utcnow().date()
        if self._cache and self._cache_timestamp and self._cache_timestamp.date() == today:
            return self._cache

        recommendation = await self.engine.generate_recommendation()
        if recommendation:
            self._cache = recommendation
            self._cache_timestamp = datetime.utcnow()
        return recommendation

    async def get_recommendation_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recommendation history."""
        # TODO: Implement database storage in Epic 4
        current = await self.get_today_recommendation()
        if current:
            return [current]
        return []

