"""CRUD helpers."""
from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select, desc
from app.db.models import RecommendationORM, RunLogORM, BacktestResultORM


def create_recommendation(db: Session, payload: dict) -> RecommendationORM:
    """Create recommendation with analysis text."""
    from app.quant.narrative import build_narrative
    
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    
    # Generate analysis text if not provided
    analysis = payload.get("analysis", "")
    if not analysis:
        analysis = build_narrative(payload)
    
    rec = RecommendationORM(
        date=date_str,
        signal=payload["signal"],
        entry_min=payload["entry_range"]["min"],
        entry_max=payload["entry_range"]["max"],
        entry_optimal=payload["entry_range"]["optimal"],
        stop_loss=payload["stop_loss_take_profit"]["stop_loss"],
        take_profit=payload["stop_loss_take_profit"]["take_profit"],
        stop_loss_pct=payload["stop_loss_take_profit"]["stop_loss_pct"],
        take_profit_pct=payload["stop_loss_take_profit"]["take_profit_pct"],
        confidence=payload["confidence"],
        current_price=payload["current_price"],
        indicators=payload.get("indicators", {}),
        risk_metrics=payload.get("risk_metrics", {}),
        factors=payload.get("factors", {}),
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


def log_run(db: Session, run_type: str, status: str, message: str = "") -> RunLogORM:
    now = datetime.utcnow()
    rl = RunLogORM(run_type=run_type, status=status, message=message, started_at=now, finished_at=now)
    db.add(rl)
    db.commit()
    db.refresh(rl)
    return rl


def get_last_run(db: Session, run_type: str | None = None) -> RunLogORM | None:
    stmt = select(RunLogORM)
    if run_type:
        from sqlalchemy import and_
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
