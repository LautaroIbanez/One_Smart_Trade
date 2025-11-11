"""CRUD helpers."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.db.models import BacktestResultORM, RecommendationORM, RunLogORM


def _normalise_date_from_market_timestamp(market_timestamp: str | None, fallback: datetime) -> str:
    """
    Try to derive the recommendation date from the market timestamp.

    Falls back to the provided datetime (typically utcnow) if the timestamp is
    missing or cannot be parsed.
    """
    if not market_timestamp:
        return fallback.strftime("%Y-%m-%d")

    try:
        parsed = datetime.fromisoformat(market_timestamp)
    except ValueError:
        return fallback.strftime("%Y-%m-%d")
    return parsed.date().isoformat()


def _apply_payload_to_recommendation(rec: RecommendationORM, data: dict[str, Any]) -> None:
    """Mutate an existing RecommendationORM with the payload fields."""
    rec.signal = data["signal"]
    rec.entry_min = data["entry_range"]["min"]
    rec.entry_max = data["entry_range"]["max"]
    rec.entry_optimal = data["entry_range"]["optimal"]
    rec.stop_loss = data["stop_loss_take_profit"]["stop_loss"]
    rec.take_profit = data["stop_loss_take_profit"]["take_profit"]
    rec.stop_loss_pct = data["stop_loss_take_profit"]["stop_loss_pct"]
    rec.take_profit_pct = data["stop_loss_take_profit"]["take_profit_pct"]
    rec.confidence = data["confidence"]
    rec.current_price = data["current_price"]
    rec.market_timestamp = data.get("market_timestamp")
    rec.spot_source = data.get("spot_source", rec.spot_source)
    rec.indicators = data.get("indicators", {})
    rec.factors = data.get("factors", {})
    rec.risk_metrics = data["risk_metrics"]
    rec.signal_breakdown = data.get("signal_breakdown", {})
    rec.analysis = data["analysis"]
    rec.created_at = datetime.utcnow()


def create_recommendation(db: Session, payload: dict) -> RecommendationORM:
    """Create recommendation with persisted analysis."""
    from app.quant.narrative import build_narrative

    now = datetime.utcnow()
    data: dict[str, Any] = payload.copy()

    if not data.get("analysis"):
        data["analysis"] = build_narrative(data)

    market_timestamp = data.get("market_timestamp")
    date_str = _normalise_date_from_market_timestamp(market_timestamp, now)

    if not market_timestamp:
        market_timestamp = f"{date_str}T00:00:00+00:00"
        data["market_timestamp"] = market_timestamp

    data.setdefault("spot_source", "1d")

    record: dict[str, Any] = {
        "date": date_str,
        "signal": data["signal"],
        "entry_min": data["entry_range"]["min"],
        "entry_max": data["entry_range"]["max"],
        "entry_optimal": data["entry_range"]["optimal"],
        "stop_loss": data["stop_loss_take_profit"]["stop_loss"],
        "take_profit": data["stop_loss_take_profit"]["take_profit"],
        "stop_loss_pct": data["stop_loss_take_profit"]["stop_loss_pct"],
        "take_profit_pct": data["stop_loss_take_profit"]["take_profit_pct"],
        "confidence": data["confidence"],
        "current_price": data["current_price"],
        "market_timestamp": market_timestamp,
        "spot_source": data.get("spot_source", "1d"),
        "indicators": data.get("indicators", {}),
        "factors": data.get("factors", {}),
        "risk_metrics": data["risk_metrics"],
        "signal_breakdown": data.get("signal_breakdown", {}),
        "analysis": data["analysis"],
        "created_at": now,
    }

    dialect_name = getattr(getattr(db, "bind", None), "dialect", None)
    if dialect_name and dialect_name.name == "sqlite":
        stmt = sqlite_insert(RecommendationORM).values(record)
        update_values = {k: v for k, v in record.items() if k not in {"date", "market_timestamp"}}
        stmt = stmt.on_conflict_do_update(
            index_elements=["date", "market_timestamp"],
            set_=update_values,
        )
        db.execute(stmt)
        db.commit()
        rec = (
            db.execute(
                select(RecommendationORM)
                .where(RecommendationORM.date == date_str)
                .where(RecommendationORM.market_timestamp == market_timestamp)
            )
            .scalars()
            .first()
        )
        if rec is None:
            raise RuntimeError("Failed to persist recommendation snapshot")
        return rec

    # Fallback path for non-SQLite databases
    query = select(RecommendationORM).where(RecommendationORM.date == date_str)
    if market_timestamp:
        query = query.where(RecommendationORM.market_timestamp == market_timestamp)
    existing = db.execute(query.order_by(desc(RecommendationORM.created_at))).scalars().first()

    if existing:
        _apply_payload_to_recommendation(existing, data)
        db.commit()
        db.refresh(existing)
        return existing

    rec = RecommendationORM(**record)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def get_latest_recommendation(db: Session) -> RecommendationORM | None:
    stmt = select(RecommendationORM).order_by(desc(RecommendationORM.created_at)).limit(1)
    return db.execute(stmt).scalars().first()


def get_recommendation_history(db: Session, limit: int = 30) -> list[RecommendationORM]:
    stmt = select(RecommendationORM).order_by(desc(RecommendationORM.created_at)).limit(limit)
    return list(db.execute(stmt).scalars().all())


def log_run(db: Session, run_type: str, status: str, message: str = "", details: dict | None = None) -> RunLogORM:
    now = datetime.utcnow()
    formatted_message = message
    if details:
        try:
            details_json = json.dumps(details, default=str)
        except TypeError:
            details_json = str(details)
        formatted_message = f"{message} | details={details_json}" if message else details_json

    rl = RunLogORM(run_type=run_type, status=status, message=formatted_message, started_at=now, finished_at=now)
    db.add(rl)
    db.commit()
    db.refresh(rl)
    return rl


def get_last_run(db: Session, run_type: str | None = None) -> RunLogORM | None:
    stmt = select(RunLogORM)
    if run_type:
        stmt = stmt.where(RunLogORM.run_type == run_type)
    stmt = stmt.order_by(desc(RunLogORM.finished_at)).limit(1)
    return db.execute(stmt).scalars().first()


def save_backtest_result(db: Session, version: str, start_date: str, end_date: str, metrics: dict) -> BacktestResultORM:
    """Save versioned backtest result."""
    result = BacktestResultORM(
        version=version,
        start_date=start_date,
        end_date=end_date,
        metrics=metrics,
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return result


def get_latest_backtest_result(db: Session) -> BacktestResultORM | None:
    """Get latest backtest result."""
    stmt = select(BacktestResultORM).order_by(desc(BacktestResultORM.created_at)).limit(1)
    return db.execute(stmt).scalars().first()
