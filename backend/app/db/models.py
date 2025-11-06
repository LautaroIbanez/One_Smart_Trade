"""SQLAlchemy models for recommendations and runs."""
from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Float, Integer, DateTime, JSON
from app.core.database import Base


class RecommendationORM(Base):
    __tablename__ = "recommendations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM-DD
    signal: Mapped[str] = mapped_column(String(8))
    entry_min: Mapped[float] = mapped_column(Float)
    entry_max: Mapped[float] = mapped_column(Float)
    entry_optimal: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float] = mapped_column(Float)
    take_profit: Mapped[float] = mapped_column(Float)
    stop_loss_pct: Mapped[float] = mapped_column(Float)
    take_profit_pct: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    current_price: Mapped[float] = mapped_column(Float)
    indicators: Mapped[dict] = mapped_column(JSON)
    risk_metrics: Mapped[dict] = mapped_column(JSON)
    factors: Mapped[dict] = mapped_column(JSON, default={})
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RunLogORM(Base):
    __tablename__ = "run_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_type: Mapped[str] = mapped_column(String(32))  # ingestion|signal
    status: Mapped[str] = mapped_column(String(16))  # success|error
    message: Mapped[str] = mapped_column(String(255), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


