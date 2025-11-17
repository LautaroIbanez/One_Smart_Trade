"""Logging helpers for signal emissions and realised outcomes."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.logging import logger
from app.db.models import SignalOutcomeORM

OutcomeLabel = Literal["win", "loss", "breakeven", "open"]


@dataclass(slots=True)
class SignalLogRecord:
    """Structured payload for signal emission logging."""

    strategy_id: str
    signal: str
    confidence_raw: float
    decision_timestamp: datetime = field(default_factory=datetime.utcnow)
    confidence_calibrated: float | None = None
    recommendation_id: int | None = None
    market_regime: str | None = None
    vol_bucket: str | None = None
    features_regimen: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    outcome: OutcomeLabel | None = None
    pnl_pct: float | None = None
    horizon_minutes: int | None = None


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _sanitize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(v) for v in value]
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, (float, int, str, bool)) or value is None:
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        try:
            return int(value)
        except (TypeError, ValueError):
            return str(value)


def _ensure_serializable(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert any non-serializable values to native Python types."""
    return {key: _sanitize_value(value) for key, value in payload.items()}


def log_signal_event(record: SignalLogRecord, *, session: Session | None = None) -> int:
    """Persist a signal emission into the signal_outcomes table.

    Args:
        record: Structured data to persist
        session: Optional caller-managed DB session

    Returns:
        Primary key of the stored row
    """

    db = session or SessionLocal()
    owns_session = session is None
    try:
        orm = SignalOutcomeORM(
            strategy_id=record.strategy_id,
            signal=record.signal,
            decision_timestamp=record.decision_timestamp,
            confidence_raw=float(record.confidence_raw),
            confidence_calibrated=float(record.confidence_calibrated) if record.confidence_calibrated is not None else None,
            recommendation_id=record.recommendation_id,
            market_regime=record.market_regime,
            vol_bucket=record.vol_bucket,
            features_regimen=_ensure_serializable(record.features_regimen),
            metadata=_ensure_serializable(record.metadata),
            outcome=record.outcome,
            pnl_pct=float(record.pnl_pct) if record.pnl_pct is not None else None,
            horizon_minutes=record.horizon_minutes,
        )
        db.add(orm)
        db.commit()
        db.refresh(orm)
        return orm.id
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to persist signal emission",
            extra={
                "strategy_id": record.strategy_id,
                "signal": record.signal,
            },
        )
        raise
    finally:
        if owns_session:
            db.close()


def update_signal_outcome(
    record_id: int,
    *,
    outcome: OutcomeLabel,
    pnl_pct: float | None = None,
    session: Session | None = None,
) -> None:
    """Update a signal record once the realised outcome is known."""
    db = session or SessionLocal()
    owns_session = session is None
    try:
        row = db.get(SignalOutcomeORM, record_id)
        if not row:
            raise ValueError(f"signal_outcomes row {record_id} not found")
        row.outcome = outcome
        if pnl_pct is not None:
            row.pnl_pct = float(pnl_pct)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to update signal outcome", extra={"record_id": record_id})
        raise
    finally:
        if owns_session:
            db.close()


def update_signal_outcome_for_recommendation(
    recommendation_id: int,
    *,
    outcome: OutcomeLabel,
    pnl_pct: float | None = None,
    session: Session | None = None,
) -> None:
    """Update a signal record tied to a recommendation."""
    db = session or SessionLocal()
    owns_session = session is None
    try:
        stmt = (
            select(SignalOutcomeORM)
            .where(SignalOutcomeORM.recommendation_id == recommendation_id)
            .order_by(SignalOutcomeORM.id.desc())
            .limit(1)
        )
        row = db.execute(stmt).scalars().first()
        if not row:
            raise ValueError(f"No signal_outcomes row linked to recommendation {recommendation_id}")
        row.outcome = outcome
        if pnl_pct is not None:
            row.pnl_pct = float(pnl_pct)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to update signal outcome for recommendation",
            extra={"recommendation_id": recommendation_id},
        )
        raise
    finally:
        if owns_session:
            db.close()

