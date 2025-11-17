"""add signal outcomes table

Revision ID: 014_add_signal_outcomes_table
Revises: 013_add_performance_periodic
Create Date: 2025-11-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "014_add_signal_outcomes_table"
down_revision = "013_add_performance_periodic"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signal_outcomes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("recommendation_id", sa.Integer(), sa.ForeignKey("recommendations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("signal", sa.String(length=8), nullable=False),
        sa.Column("decision_timestamp", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("confidence_raw", sa.Float(), nullable=False),
        sa.Column("confidence_calibrated", sa.Float(), nullable=True),
        sa.Column("market_regime", sa.String(length=32), nullable=True),
        sa.Column("vol_bucket", sa.String(length=32), nullable=True),
        sa.Column("features_regimen", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("outcome", sa.String(length=16), nullable=True),
        sa.Column("pnl_pct", sa.Float(), nullable=True),
        sa.Column("horizon_minutes", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), server_onupdate=sa.func.now()),
    )
    op.create_index("ix_signal_outcomes_recommendation_id", "signal_outcomes", ["recommendation_id"])
    op.create_index("ix_signal_outcomes_strategy_id", "signal_outcomes", ["strategy_id"])
    op.create_index("ix_signal_outcomes_decision_timestamp", "signal_outcomes", ["decision_timestamp"])
    op.create_index("ix_signal_outcomes_market_regime", "signal_outcomes", ["market_regime"])
    op.create_index("ix_signal_outcomes_vol_bucket", "signal_outcomes", ["vol_bucket"])
    op.create_index("ix_signal_outcomes_outcome", "signal_outcomes", ["outcome"])
    op.create_index("ix_signal_outcomes_created_at", "signal_outcomes", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_signal_outcomes_created_at", table_name="signal_outcomes")
    op.drop_index("ix_signal_outcomes_outcome", table_name="signal_outcomes")
    op.drop_index("ix_signal_outcomes_vol_bucket", table_name="signal_outcomes")
    op.drop_index("ix_signal_outcomes_market_regime", table_name="signal_outcomes")
    op.drop_index("ix_signal_outcomes_decision_timestamp", table_name="signal_outcomes")
    op.drop_index("ix_signal_outcomes_strategy_id", table_name="signal_outcomes")
    op.drop_index("ix_signal_outcomes_recommendation_id", table_name="signal_outcomes")
    op.drop_table("signal_outcomes")

