"""Service for validating SL/TP levels against historical orderbook data."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from app.core.database import SessionLocal
from app.core.logging import logger
from app.data.orderbook import OrderBookRepository, OrderBookSnapshot
from app.db.crud import get_latest_recommendation
from app.db.models import RecommendationORM
from sqlalchemy import select


@dataclass
class SLTPValidationResult:
    """Result of validating a single recommendation's SL/TP levels."""
    
    recommendation_id: int
    signal: str
    entry_optimal: float
    stop_loss: float
    take_profit: float
    created_at: datetime
    closed_at: datetime | None
    
    # Validation results
    sl_touched: bool
    tp_touched: bool
    sl_touch_timestamp: datetime | None
    tp_touch_timestamp: datetime | None
    sl_touch_price: float | None
    tp_touch_price: float | None
    
    # Orderbook metrics
    min_price_reached: float | None
    max_price_reached: float | None
    sl_distance_bps: float | None  # Distance from entry to SL in basis points
    tp_distance_bps: float | None  # Distance from entry to TP in basis points
    
    # Validation metadata
    orderbook_snapshots_checked: int
    validation_window_start: datetime
    validation_window_end: datetime


@dataclass
class ValidationReport:
    """Report summarizing SL/TP validation results."""
    
    period_start: datetime
    period_end: datetime
    total_recommendations: int
    recommendations_validated: int
    
    # Fulfillment metrics
    sl_fulfillment_rate: float  # Percentage of SL levels that were touched
    tp_fulfillment_rate: float  # Percentage of TP levels that were touched
    both_fulfilled_rate: float  # Percentage where both were touched
    neither_fulfilled_rate: float  # Percentage where neither was touched
    
    # Distance metrics
    avg_sl_distance_bps: float | None
    avg_tp_distance_bps: float | None
    min_sl_distance_bps: float | None
    max_sl_distance_bps: float | None
    min_tp_distance_bps: float | None
    max_tp_distance_bps: float | None
    
    # Recommendations that failed validation
    low_fulfillment_recommendations: list[dict[str, Any]]
    
    # Heuristic adjustment recommendations
    heuristic_adjustment_needed: bool
    adjustment_reason: str | None


class SLTPValidationService:
    """Service for validating SL/TP levels against historical orderbook data."""
    
    def __init__(self, venue: str = "binance", symbol: str = "BTCUSDT"):
        """
        Initialize validation service.
        
        Args:
            venue: Trading venue (default: "binance")
            symbol: Trading symbol (default: "BTCUSDT")
        """
        self.venue = venue
        self.symbol = symbol
        self.orderbook_repo = OrderBookRepository(venue=venue)
    
    async def validate_recommendation(
        self,
        recommendation: RecommendationORM,
        *,
        lookahead_days: int = 7,
    ) -> SLTPValidationResult | None:
        """
        Validate SL/TP levels for a single recommendation against orderbook data.
        
        Args:
            recommendation: Recommendation to validate
            lookahead_days: Number of days to look ahead from creation date
            
        Returns:
            Validation result or None if validation failed
        """
        if recommendation.signal == "HOLD":
            return None
        
        if not recommendation.stop_loss or not recommendation.take_profit:
            logger.warning(f"Recommendation {recommendation.id} missing SL/TP levels")
            return None
        
        # Determine validation window
        validation_start = pd.Timestamp(recommendation.created_at)
        if recommendation.closed_at:
            validation_end = pd.Timestamp(recommendation.closed_at)
        else:
            validation_end = validation_start + pd.Timedelta(days=lookahead_days)
        
        # Load orderbook snapshots for the validation window
        try:
            snapshots = await self.orderbook_repo.load(
                symbol=self.symbol,
                start=validation_start,
                end=validation_end,
            )
        except Exception as e:
            logger.error(f"Failed to load orderbook for recommendation {recommendation.id}: {e}")
            return None
        
        if not snapshots:
            logger.warning(f"No orderbook snapshots found for recommendation {recommendation.id}")
            return None
        
        # Validate SL/TP levels
        sl_touched = False
        tp_touched = False
        sl_touch_timestamp = None
        tp_touch_timestamp = None
        sl_touch_price = None
        tp_touch_price = None
        min_price = None
        max_price = None
        
        entry = recommendation.entry_optimal
        sl = recommendation.stop_loss
        tp = recommendation.take_profit
        signal = recommendation.signal
        
        for snapshot in snapshots:
            best_bid = snapshot.best_bid
            best_ask = snapshot.best_ask
            
            if best_bid is None or best_ask is None:
                continue
            
            # Track min/max prices reached
            if min_price is None or best_bid < min_price:
                min_price = best_bid
            if max_price is None or best_ask > max_price:
                max_price = best_ask
            
            # Check if SL was touched
            # For BUY: SL is below entry, check if price went below SL
            # For SELL: SL is above entry, check if price went above SL
            if signal == "BUY":
                if not sl_touched and best_bid <= sl:
                    sl_touched = True
                    sl_touch_timestamp = snapshot.timestamp.to_pydatetime()
                    sl_touch_price = best_bid
                if not tp_touched and best_ask >= tp:
                    tp_touched = True
                    tp_touch_timestamp = snapshot.timestamp.to_pydatetime()
                    tp_touch_price = best_ask
            elif signal == "SELL":
                if not sl_touched and best_ask >= sl:
                    sl_touched = True
                    sl_touch_timestamp = snapshot.timestamp.to_pydatetime()
                    sl_touch_price = best_ask
                if not tp_touched and best_bid <= tp:
                    tp_touched = True
                    tp_touch_timestamp = snapshot.timestamp.to_pydatetime()
                    tp_touch_price = best_bid
        
        # Calculate distances in basis points
        sl_distance_bps = abs((sl - entry) / entry * 10000) if entry > 0 else None
        tp_distance_bps = abs((tp - entry) / entry * 10000) if entry > 0 else None
        
        return SLTPValidationResult(
            recommendation_id=recommendation.id,
            signal=signal,
            entry_optimal=entry,
            stop_loss=sl,
            take_profit=tp,
            created_at=recommendation.created_at,
            closed_at=recommendation.closed_at,
            sl_touched=sl_touched,
            tp_touched=tp_touched,
            sl_touch_timestamp=sl_touch_timestamp,
            tp_touch_timestamp=tp_touch_timestamp,
            sl_touch_price=sl_touch_price,
            tp_touch_price=tp_touch_price,
            min_price_reached=min_price,
            max_price_reached=max_price,
            sl_distance_bps=sl_distance_bps,
            tp_distance_bps=tp_distance_bps,
            orderbook_snapshots_checked=len(snapshots),
            validation_window_start=validation_start.to_pydatetime(),
            validation_window_end=validation_end.to_pydatetime(),
        )
    
    async def validate_period(
        self,
        start_date: datetime,
        end_date: datetime,
        *,
        lookahead_days: int = 7,
        fulfillment_threshold: float = 0.7,
    ) -> ValidationReport:
        """
        Validate all recommendations in a time period.
        
        Args:
            start_date: Start of validation period
            end_date: End of validation period
            lookahead_days: Days to look ahead for validation
            fulfillment_threshold: Minimum fulfillment rate to consider acceptable (default: 70%)
            
        Returns:
            Validation report with metrics and recommendations
        """
        # Query recommendations in period
        with SessionLocal() as db:
            try:
                stmt = (
                    select(RecommendationORM)
                    .where(RecommendationORM.created_at >= start_date)
                    .where(RecommendationORM.created_at <= end_date)
                    .where(RecommendationORM.signal.in_(["BUY", "SELL"]))
                    .where(RecommendationORM.stop_loss.isnot(None))
                    .where(RecommendationORM.take_profit.isnot(None))
                    .order_by(RecommendationORM.created_at)
                )
                recommendations = list(db.execute(stmt).scalars().all())
            finally:
                db.close()
        
        if not recommendations:
            return ValidationReport(
                period_start=start_date,
                period_end=end_date,
                total_recommendations=0,
                recommendations_validated=0,
                sl_fulfillment_rate=0.0,
                tp_fulfillment_rate=0.0,
                both_fulfilled_rate=0.0,
                neither_fulfilled_rate=0.0,
                avg_sl_distance_bps=None,
                avg_tp_distance_bps=None,
                min_sl_distance_bps=None,
                max_sl_distance_bps=None,
                min_tp_distance_bps=None,
                max_tp_distance_bps=None,
                low_fulfillment_recommendations=[],
                heuristic_adjustment_needed=False,
                adjustment_reason=None,
            )
        
        # Validate each recommendation
        validation_results: list[SLTPValidationResult] = []
        for rec in recommendations:
            result = await self.validate_recommendation(rec, lookahead_days=lookahead_days)
            if result:
                validation_results.append(result)
        
        if not validation_results:
            return ValidationReport(
                period_start=start_date,
                period_end=end_date,
                total_recommendations=len(recommendations),
                recommendations_validated=0,
                sl_fulfillment_rate=0.0,
                tp_fulfillment_rate=0.0,
                both_fulfilled_rate=0.0,
                neither_fulfilled_rate=0.0,
                avg_sl_distance_bps=None,
                avg_tp_distance_bps=None,
                min_sl_distance_bps=None,
                max_sl_distance_bps=None,
                min_tp_distance_bps=None,
                max_tp_distance_bps=None,
                low_fulfillment_recommendations=[],
                heuristic_adjustment_needed=False,
                adjustment_reason=None,
            )
        
        # Calculate fulfillment metrics
        total = len(validation_results)
        sl_touched_count = sum(1 for r in validation_results if r.sl_touched)
        tp_touched_count = sum(1 for r in validation_results if r.tp_touched)
        both_touched_count = sum(1 for r in validation_results if r.sl_touched and r.tp_touched)
        neither_touched_count = sum(1 for r in validation_results if not r.sl_touched and not r.tp_touched)
        
        sl_fulfillment_rate = (sl_touched_count / total) * 100.0 if total > 0 else 0.0
        tp_fulfillment_rate = (tp_touched_count / total) * 100.0 if total > 0 else 0.0
        both_fulfilled_rate = (both_touched_count / total) * 100.0 if total > 0 else 0.0
        neither_fulfilled_rate = (neither_touched_count / total) * 100.0 if total > 0 else 0.0
        
        # Calculate distance metrics
        sl_distances = [r.sl_distance_bps for r in validation_results if r.sl_distance_bps is not None]
        tp_distances = [r.tp_distance_bps for r in validation_results if r.tp_distance_bps is not None]
        
        avg_sl_distance_bps = sum(sl_distances) / len(sl_distances) if sl_distances else None
        avg_tp_distance_bps = sum(tp_distances) / len(tp_distances) if tp_distances else None
        min_sl_distance_bps = min(sl_distances) if sl_distances else None
        max_sl_distance_bps = max(sl_distances) if sl_distances else None
        min_tp_distance_bps = min(tp_distances) if tp_distances else None
        max_tp_distance_bps = max(tp_distances) if tp_distances else None
        
        # Identify low fulfillment recommendations
        low_fulfillment = []
        for result in validation_results:
            if not result.sl_touched and not result.tp_touched:
                low_fulfillment.append({
                    "recommendation_id": result.recommendation_id,
                    "signal": result.signal,
                    "entry": result.entry_optimal,
                    "stop_loss": result.stop_loss,
                    "take_profit": result.take_profit,
                    "sl_distance_bps": result.sl_distance_bps,
                    "tp_distance_bps": result.tp_distance_bps,
                    "min_price_reached": result.min_price_reached,
                    "max_price_reached": result.max_price_reached,
                    "created_at": result.created_at.isoformat(),
                })
        
        # Determine if heuristic adjustment is needed
        heuristic_adjustment_needed = False
        adjustment_reason = None
        
        if sl_fulfillment_rate < fulfillment_threshold * 100:
            heuristic_adjustment_needed = True
            adjustment_reason = f"SL fulfillment rate ({sl_fulfillment_rate:.1f}%) below threshold ({fulfillment_threshold * 100:.1f}%)"
        elif tp_fulfillment_rate < fulfillment_threshold * 100:
            heuristic_adjustment_needed = True
            adjustment_reason = f"TP fulfillment rate ({tp_fulfillment_rate:.1f}%) below threshold ({fulfillment_threshold * 100:.1f}%)"
        elif neither_fulfilled_rate > (1 - fulfillment_threshold) * 100:
            heuristic_adjustment_needed = True
            adjustment_reason = f"Neither SL nor TP fulfilled in {neither_fulfilled_rate:.1f}% of cases (threshold: {(1 - fulfillment_threshold) * 100:.1f}%)"
        
        return ValidationReport(
            period_start=start_date,
            period_end=end_date,
            total_recommendations=len(recommendations),
            recommendations_validated=total,
            sl_fulfillment_rate=sl_fulfillment_rate,
            tp_fulfillment_rate=tp_fulfillment_rate,
            both_fulfilled_rate=both_fulfilled_rate,
            neither_fulfilled_rate=neither_fulfilled_rate,
            avg_sl_distance_bps=avg_sl_distance_bps,
            avg_tp_distance_bps=avg_tp_distance_bps,
            min_sl_distance_bps=min_sl_distance_bps,
            max_sl_distance_bps=max_sl_distance_bps,
            min_tp_distance_bps=min_tp_distance_bps,
            max_tp_distance_bps=max_tp_distance_bps,
            low_fulfillment_recommendations=low_fulfillment,
            heuristic_adjustment_needed=heuristic_adjustment_needed,
            adjustment_reason=adjustment_reason,
        )
    
    async def generate_weekly_report(
        self,
        *,
        weeks_back: int = 1,
        fulfillment_threshold: float = 0.7,
    ) -> dict[str, Any]:
        """
        Generate weekly validation report.
        
        Args:
            weeks_back: Number of weeks to look back (default: 1)
            fulfillment_threshold: Minimum fulfillment rate (default: 0.7)
            
        Returns:
            Report dictionary with metrics and recommendations
        """
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(weeks=weeks_back)
        
        report = await self.validate_period(
            start_date=start_date,
            end_date=end_date,
            fulfillment_threshold=fulfillment_threshold,
        )
        
        # Format report as dictionary
        return {
            "period": {
                "start": report.period_start.isoformat(),
                "end": report.period_end.isoformat(),
                "weeks": weeks_back,
            },
            "summary": {
                "total_recommendations": report.total_recommendations,
                "recommendations_validated": report.recommendations_validated,
            },
            "fulfillment_metrics": {
                "sl_fulfillment_rate_pct": round(report.sl_fulfillment_rate, 2),
                "tp_fulfillment_rate_pct": round(report.tp_fulfillment_rate, 2),
                "both_fulfilled_rate_pct": round(report.both_fulfilled_rate, 2),
                "neither_fulfilled_rate_pct": round(report.neither_fulfilled_rate, 2),
            },
            "distance_metrics": {
                "avg_sl_distance_bps": round(report.avg_sl_distance_bps, 2) if report.avg_sl_distance_bps else None,
                "avg_tp_distance_bps": round(report.avg_tp_distance_bps, 2) if report.avg_tp_distance_bps else None,
                "min_sl_distance_bps": round(report.min_sl_distance_bps, 2) if report.min_sl_distance_bps else None,
                "max_sl_distance_bps": round(report.max_sl_distance_bps, 2) if report.max_sl_distance_bps else None,
                "min_tp_distance_bps": round(report.min_tp_distance_bps, 2) if report.min_tp_distance_bps else None,
                "max_tp_distance_bps": round(report.max_tp_distance_bps, 2) if report.max_tp_distance_bps else None,
            },
            "low_fulfillment_recommendations": report.low_fulfillment_recommendations,
            "heuristic_adjustment": {
                "needed": report.heuristic_adjustment_needed,
                "reason": report.adjustment_reason,
            },
            "recommendations": [
                {
                    "action": "review_sl_heuristic" if report.sl_fulfillment_rate < fulfillment_threshold * 100 else "review_tp_heuristic" if report.tp_fulfillment_rate < fulfillment_threshold * 100 else "review_heuristics",
                    "details": report.adjustment_reason,
                }
            ] if report.heuristic_adjustment_needed else [],
        }

