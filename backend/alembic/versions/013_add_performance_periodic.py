"""add performance_periodic table

Revision ID: 013_add_performance_periodic
Revises: 012_add_knowledge_base
Create Date: 2025-11-15
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "013_add_performance_periodic"
down_revision = "012_add_knowledge_base"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "performance_periodic",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(length=128), nullable=False, index=True),
        sa.Column("period", sa.String(length=10), nullable=False, index=True),
        sa.Column("horizon", sa.Enum("monthly", "quarterly", name="periodichorizon"), nullable=False, index=True),
        sa.Column("mean", sa.Float(), nullable=False),
        sa.Column("std", sa.Float(), nullable=False),
        sa.Column("p25", sa.Float(), nullable=False),
        sa.Column("p75", sa.Float(), nullable=False),
        sa.Column("skew", sa.Float(), nullable=False),
        sa.Column("kurtosis", sa.Float(), nullable=False),
        sa.Column("negative_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_performance_periodic_run_period", "performance_periodic", ["run_id", "period"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_performance_periodic_run_period", table_name="performance_periodic")
    op.drop_table("performance_periodic")


