"""SQLAlchemy models for recommendations and runs."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from sqlalchemy import Enum as SAEnum
from enum import Enum

class RecommendationORM(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        UniqueConstraint("date", "market_timestamp", name="uq_recommendations_date_market_timestamp"),
    )
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
    confidence_calibrated: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_price: Mapped[float] = mapped_column(Float)
    market_timestamp: Mapped[str | None] = mapped_column(String(32), nullable=True)
    spot_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    indicators: Mapped[dict] = mapped_column(JSON, default={})
    risk_metrics: Mapped[dict] = mapped_column(JSON, default={})
    factors: Mapped[dict] = mapped_column(JSON, default={})
    signal_breakdown: Mapped[dict] = mapped_column(JSON, default={})
    analysis: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(16), default="closed", index=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_price_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    code_commit: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    dataset_version: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    params_digest: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class SignalOutcomeORM(Base):
    """Log raw signal emissions and realised outcomes for calibration."""

    __tablename__ = "signal_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recommendation_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("recommendations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    strategy_id: Mapped[str] = mapped_column(String(64), index=True)
    signal: Mapped[str] = mapped_column(String(8))
    decision_timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    confidence_raw: Mapped[float] = mapped_column(Float)
    confidence_calibrated: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_regime: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    vol_bucket: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    features_regimen: Mapped[dict] = mapped_column(JSON, default=dict)
    metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    outcome: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    pnl_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    horizon_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RunLogORM(Base):
    __tablename__ = "run_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_type: Mapped[str] = mapped_column(String(32))  # ingestion|signal
    status: Mapped[str] = mapped_column(String(16))  # success|error
    message: Mapped[str] = mapped_column(String(255), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BacktestResultORM(Base):
    """Store versioned backtest results."""
    __tablename__ = "backtest_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(20), index=True)  # e.g., "0.1.0"
    start_date: Mapped[str] = mapped_column(String(20))
    end_date: Mapped[str] = mapped_column(String(20))
    metrics: Mapped[dict] = mapped_column(JSON)  # All calculated metrics
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class StrategyChampionORM(Base):
    """History of champion strategy promotions."""

    __tablename__ = "strategy_champions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    params_id: Mapped[str] = mapped_column(String(64), index=True)
    params_version: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    objective: Mapped[str] = mapped_column(String(64))
    target_metric: Mapped[str] = mapped_column(String(64))
    target_value: Mapped[float] = mapped_column(Float)
    score: Mapped[float] = mapped_column(Float)
    metrics: Mapped[dict] = mapped_column(JSON)
    trained_on_regime: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    statistical_test: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    engine_args: Mapped[dict] = mapped_column(JSON, default={})
    execution_overrides: Mapped[dict] = mapped_column(JSON, default={})
    drawdown_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    end_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    promoted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    replaced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    previous_champion_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    previous_params_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    previous_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    previous_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class DataRunORM(Base):
    """Track ingestion runs for completeness monitoring."""

    __tablename__ = "data_runs"
    __table_args__ = (
        UniqueConstraint("venue", "symbol", "interval", "start_time", "end_time", name="uq_data_runs_window"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    venue: Mapped[str] = mapped_column(String(32), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    interval: Mapped[str] = mapped_column(String(16), index=True)
    start_time: Mapped[str] = mapped_column(String(32))
    end_time: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), index=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    message: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ExportAuditORM(Base):
    """Audit trail for recommendation exports."""

    __tablename__ = "exports_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    filters: Mapped[dict] = mapped_column(JSON, default={})
    format: Mapped[str] = mapped_column(String(16))  # csv|parquet
    record_count: Mapped[int] = mapped_column(Integer)
    file_hash: Mapped[str] = mapped_column(String(64))  # SHA-256
    file_size_bytes: Mapped[int] = mapped_column(Integer)
    export_params: Mapped[dict] = mapped_column(JSON, default={})
    exported_by: Mapped[str] = mapped_column(String(128), default="anonymous", index=True)  # User ID or identifier
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class PeriodicHorizon(str, Enum):
    monthly = "monthly"
    quarterly = "quarterly"


class PerformancePeriodicORM(Base):
    """Aggregated periodic performance metrics (monthly/quarterly)."""

    __tablename__ = "performance_periodic"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)  # e.g., params_digest or external id
    period: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM or YYYY-QX
    horizon: Mapped[PeriodicHorizon] = mapped_column(SAEnum(PeriodicHorizon), index=True)
    mean: Mapped[float] = mapped_column(Float)
    std: Mapped[float] = mapped_column(Float)
    p25: Mapped[float] = mapped_column(Float)
    p75: Mapped[float] = mapped_column(Float)
    skew: Mapped[float] = mapped_column(Float)
    kurtosis: Mapped[float] = mapped_column(Float)
    negative_flag: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class UserRiskStateORM(Base):
    """User psychological risk state tracking."""

    __tablename__ = "user_risk_state"

    user_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    current_drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0)
    longest_losing_streak: Mapped[int] = mapped_column(Integer, default=0)
    current_losing_streak: Mapped[int] = mapped_column(Integer, default=0)
    longest_winning_streak: Mapped[int] = mapped_column(Integer, default=0)
    current_winning_streak: Mapped[int] = mapped_column(Integer, default=0)
    trades_last_24h: Mapped[int] = mapped_column(Integer, default=0)
    avg_exposure_pct: Mapped[float] = mapped_column(Float, default=0.0)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    cooldown_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    current_equity: Mapped[float] = mapped_column(Float, default=0.0)
    total_notional: Mapped[float] = mapped_column(Float, default=0.0)
    effective_leverage: Mapped[float] = mapped_column(Float, default=0.0)
    leverage_hard_stop: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    leverage_hard_stop_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, index=True)


class CooldownEventORM(Base):
    """Audit trail for cooldown events."""

    __tablename__ = "cooldown_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), index=True)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    cooldown_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(String(128))
    losing_streak: Mapped[int] = mapped_column(Integer, default=0)
    trades_last_24h: Mapped[int] = mapped_column(Integer, default=0)
    current_drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class LeverageAlertORM(Base):
    """Audit trail for leverage alerts and hard stops."""

    __tablename__ = "leverage_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), index=True)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    leverage: Mapped[float] = mapped_column(Float)
    equity: Mapped[float] = mapped_column(Float)
    notional: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float)
    alert_type: Mapped[str] = mapped_column(String(32))  # warning|hard_stop
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class KnowledgeArticleORM(Base):
    """Educational articles in the knowledge base."""

    __tablename__ = "knowledge_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # emotional_management|risk_limits|rest|journaling
    content: Mapped[str] = mapped_column(Text, nullable=False)  # Markdown content
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)  # Array of tags
    trigger_conditions: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Conditions that trigger this article
    priority: Mapped[int] = mapped_column(Integer, default=0)  # Higher priority articles shown first
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    pdf_path: Mapped[str | None] = mapped_column(String(512), nullable=True)  # Path to PDF file if available
    download_url: Mapped[str | None] = mapped_column(String(512), nullable=True)  # CDN URL for PDF download
    micro_habits: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)  # Array of actionable micro-habits
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False, index=True)  # Critical articles require reading
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class UserReadingORM(Base):
    """Track user's reading history of educational articles."""

    __tablename__ = "user_readings"
    __table_args__ = (
        UniqueConstraint("user_id", "article_id", name="uq_user_readings_user_article"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), index=True, nullable=False)
    article_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    first_read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    last_read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
    read_count: Mapped[int] = mapped_column(Integer, default=1)
    pdf_downloaded: Mapped[bool] = mapped_column(Boolean, default=False)
    pdf_downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)  # User marked as completed
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class KnowledgeEngagementORM(Base):
    """Track user engagement with educational content (downloads, views, etc.)."""

    __tablename__ = "knowledge_engagement"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), index=True, nullable=False)
    article_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    engagement_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)  # download|view|share|complete
    metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Additional context (device, referrer, etc.)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class EnsembleWeightORM(Base):
    """Store ensemble strategy weights by regime with performance metrics."""

    __tablename__ = "ensemble_weights"
    __table_args__ = (
        UniqueConstraint("regime", "strategy_name", "snapshot_date", name="uq_ensemble_weights_regime_strategy_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    regime: Mapped[str] = mapped_column(String(32), index=True, nullable=False)  # bull|bear|range|neutral
    strategy_name: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    snapshot_date: Mapped[str] = mapped_column(String(10), index=True, nullable=False)  # YYYY-MM-DD
    metrics: Mapped[dict] = mapped_column(JSON, default={})  # calmar, drawdown, hit_rate, sharpe, etc.
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class RiskAuditORM(Base):
    """Audit trail for risk validation events and blocked operations."""

    __tablename__ = "risk_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), index=True, nullable=False)
    blocked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    audit_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)  # capital_missing|overexposed|leverage_hard_stop|cooldown|risk_limit_violation
    reason: Mapped[str] = mapped_column(String(512), nullable=False)
    recommendation_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    context_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Additional context (equity, leverage, etc.)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


