"""CRUD helpers."""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import BacktestResultORM, RecommendationORM, RunLogORM


def create_recommendation(db: Session, payload: dict) -> RecommendationORM:
    """Create recommendation with persisted analysis."""
    from app.quant.narrative import build_narrative

    data = payload
    date_str = datetime.utcnow().strftime("%Y-%m-%d")

    analysis = data.get("analysis")
    if not analysis:
        analysis = build_narrative(data)

    rec = RecommendationORM(
        date=date_str,
        signal=data["signal"],
        entry_min=data["entry_range"]["min"],
        entry_max=data["entry_range"]["max"],
        entry_optimal=data["entry_range"]["optimal"],
        stop_loss=data["stop_loss_take_profit"]["stop_loss"],
        take_profit=data["stop_loss_take_profit"]["take_profit"],
        stop_loss_pct=data["stop_loss_take_profit"]["stop_loss_pct"],
        take_profit_pct=data["stop_loss_take_profit"]["take_profit_pct"],
        confidence=data["confidence"],
        current_price=data["current_price"],
        indicators=data.get("indicators", {}),
        factors=data.get("factors", {}),
        risk_metrics=data["risk_metrics"],
        analysis=analysis,
    )
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
