"""User risk state endpoints."""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from typing import Any
from uuid import UUID

from app.core.database import SessionLocal
from app.core.logging import logger
from app.db.crud import get_contextual_articles, get_leverage_alerts, get_user_risk_state, update_user_risk_state
from app.db.models import CooldownEventORM, LeverageAlertORM, UserRiskStateORM

router = APIRouter()


@router.get("/state")
async def get_user_risk_state_endpoint(
    user_id: str = Query(..., description="User UUID")
) -> dict[str, Any]:
    """
    Get user risk state with psychological metrics.
    
    Returns:
    - Current drawdown
    - Current and longest losing/winning streaks
    - Trades in last 24 hours
    - Average exposure
    - Warnings for adverse streaks or overtrading
    """
    try:
        with SessionLocal() as db:
            state = get_user_risk_state(db, user_id)
            
            if not state:
                # Initialize default state
                return {
                    "status": "ok",
                    "user_id": user_id,
                    "current_drawdown_pct": 0.0,
                    "longest_losing_streak": 0,
                    "current_losing_streak": 0,
                    "longest_winning_streak": 0,
                    "current_winning_streak": 0,
                    "trades_last_24h": 0,
                    "avg_exposure_pct": 0.0,
                    "cooldown_until": None,
                    "cooldown_reason": None,
                    "is_on_cooldown": False,
                    "cooldown_remaining_seconds": None,
                    "current_equity": 0.0,
                    "total_notional": 0.0,
                    "effective_leverage": 0.0,
                    "leverage_hard_stop": False,
                    "leverage_hard_stop_since": None,
                    "last_updated": None,
                    "warnings": [],
                }
            
            # Calculate warnings
            warnings = []
            
            # Adverse losing streak warning
            if state.current_losing_streak >= 3:
                warnings.append({
                    "type": "adverse_streak",
                    "severity": "warning" if state.current_losing_streak < 5 else "critical",
                    "message": f"Racha perdedora actual: {state.current_losing_streak} trades consecutivos",
                })
            
            # Overtrading warning
            if state.trades_last_24h >= 10:
                warnings.append({
                    "type": "overtrading",
                    "severity": "warning" if state.trades_last_24h < 20 else "critical",
                    "message": f"Sobreoperación: {state.trades_last_24h} trades en las últimas 24 horas",
                })
            
            # High drawdown warning
            if state.current_drawdown_pct >= 15.0:
                warnings.append({
                    "type": "high_drawdown",
                    "severity": "warning" if state.current_drawdown_pct < 25.0 else "critical",
                    "message": f"Drawdown alto: {state.current_drawdown_pct:.2f}%",
                })
            
            # Check cooldown status
            now = datetime.utcnow()
            is_on_cooldown = state.cooldown_until and state.cooldown_until > now.replace(tzinfo=state.cooldown_until.tzinfo) if state.cooldown_until else False
            cooldown_remaining = None
            if is_on_cooldown and state.cooldown_until:
                delta = state.cooldown_until - now.replace(tzinfo=state.cooldown_until.tzinfo)
                cooldown_remaining = max(0, int(delta.total_seconds()))
            
            # Add leverage warning if threshold exceeded
            from app.core.config import settings
            if state.effective_leverage > settings.LEVERAGE_WARNING_THRESHOLD:
                warnings.append({
                    "type": "high_leverage",
                    "severity": "critical" if state.effective_leverage > settings.LEVERAGE_HARD_STOP_THRESHOLD else "warning",
                    "message": f"Apalancamiento elevado: {state.effective_leverage:.2f}× (Umbral: {settings.LEVERAGE_HARD_STOP_THRESHOLD}×)",
                })
            
            # Get contextual educational articles with specific context
            contextual_articles = []
            trigger_type = None
            context_data = {}
            
            if is_on_cooldown:
                trigger_type = "cooldown"
                context_data = {
                    "losing_streak": state.current_losing_streak,
                    "trades_24h": state.trades_last_24h,
                    "drawdown_pct": state.current_drawdown_pct,
                }
            elif state.effective_leverage > settings.LEVERAGE_WARNING_THRESHOLD:
                trigger_type = "leverage"
                context_data = {
                    "leverage": state.effective_leverage,
                    "threshold": settings.LEVERAGE_WARNING_THRESHOLD,
                }
            elif state.current_drawdown_pct >= 10.0:
                trigger_type = "drawdown"
                context_data = {
                    "drawdown_pct": state.current_drawdown_pct,
                }
            
            if trigger_type:
                try:
                    articles = get_contextual_articles(
                        db, 
                        user_id, 
                        trigger_type=trigger_type, 
                        limit=3,
                        context_data=context_data,
                    )
                    contextual_articles = [
                        {
                            "id": a.id,
                            "title": a.title,
                            "slug": a.slug,
                            "summary": a.summary,
                            "category": a.category,
                            "micro_habits": a.micro_habits,
                            "is_critical": a.is_critical,
                        }
                        for a in articles
                    ]
                except Exception as e:
                    logger.warning(f"Failed to fetch contextual articles: {e}", exc_info=True)
            
            return {
                "status": "ok",
                "user_id": str(state.user_id),
                "current_drawdown_pct": float(state.current_drawdown_pct),
                "longest_losing_streak": state.longest_losing_streak,
                "current_losing_streak": state.current_losing_streak,
                "longest_winning_streak": state.longest_winning_streak,
                "current_winning_streak": state.current_winning_streak,
                "trades_last_24h": state.trades_last_24h,
                "avg_exposure_pct": float(state.avg_exposure_pct),
                "cooldown_until": state.cooldown_until.isoformat() if state.cooldown_until else None,
                "cooldown_reason": state.cooldown_reason,
                "is_on_cooldown": is_on_cooldown,
                "cooldown_remaining_seconds": cooldown_remaining,
                "current_equity": float(state.current_equity),
                "total_notional": float(state.total_notional),
                "effective_leverage": float(state.effective_leverage),
                "leverage_hard_stop": state.leverage_hard_stop,
                "leverage_hard_stop_since": state.leverage_hard_stop_since.isoformat() if state.leverage_hard_stop_since else None,
                "last_updated": state.last_updated.isoformat() if state.last_updated else None,
                "warnings": warnings,
                "contextual_articles": contextual_articles,
            }
    except Exception as e:
        logger.error(f"Error fetching user risk state: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/state/update")
async def update_user_risk_state_endpoint(
    user_id: str,
    trigger_update: bool = Query(False, description="Force recalculation from trades"),
) -> dict[str, Any]:
    """
    Update user risk state (usually called automatically on trade close).
    
    If trigger_update=True, recalculates state from all closed trades.
    """
    try:
        with SessionLocal() as db:
            if trigger_update:
                update_user_risk_state(db, user_id, closed_trade=None)
            
            state = get_user_risk_state(db, user_id)
            
            if not state:
                raise HTTPException(status_code=404, detail="User risk state not found")
            
            return {
                "status": "ok",
                "user_id": str(state.user_id),
                "current_drawdown_pct": float(state.current_drawdown_pct),
                "longest_losing_streak": state.longest_losing_streak,
                "current_losing_streak": state.current_losing_streak,
                "longest_winning_streak": state.longest_winning_streak,
                "current_winning_streak": state.current_winning_streak,
                "trades_last_24h": state.trades_last_24h,
                "avg_exposure_pct": float(state.avg_exposure_pct),
                "current_equity": float(state.current_equity),
                "total_notional": float(state.total_notional),
                "effective_leverage": float(state.effective_leverage),
                "leverage_hard_stop": state.leverage_hard_stop,
                "leverage_hard_stop_since": state.leverage_hard_stop_since.isoformat() if state.leverage_hard_stop_since else None,
                "last_updated": state.last_updated.isoformat() if state.last_updated else None,
            }
    except Exception as e:
        logger.error(f"Error updating user risk state: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/leverage/alerts")
async def get_leverage_alerts_endpoint(
    user_id: str = Query(..., description="User UUID"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of alerts to return"),
    alert_type: str | None = Query(None, description="Filter by alert type (warning|hard_stop)"),
    unresolved_only: bool = Query(False, description="Only return unresolved alerts"),
) -> dict[str, Any]:
    """
    Get leverage alert history for a user.
    
    Returns audit trail of leverage warnings and hard stops.
    """
    try:
        with SessionLocal() as db:
            alerts = get_leverage_alerts(
                db,
                user_id,
                limit=limit,
                alert_type=alert_type,
                unresolved_only=unresolved_only,
            )
            
            return {
                "status": "ok",
                "user_id": user_id,
                "alerts": [
                    {
                        "id": alert.id,
                        "triggered_at": alert.triggered_at.isoformat(),
                        "leverage": float(alert.leverage),
                        "equity": float(alert.equity),
                        "notional": float(alert.notional),
                        "threshold": float(alert.threshold),
                        "alert_type": alert.alert_type,
                        "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
                        "created_at": alert.created_at.isoformat(),
                    }
                    for alert in alerts
                ],
                "count": len(alerts),
            }
    except Exception as e:
        logger.error(f"Error fetching leverage alerts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

