"""Add user_risk_state table.

Revision ID: 009
Revises: 008
Create Date: 2024-01-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if using PostgreSQL
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    
    if is_postgres:
        from sqlalchemy.dialects import postgresql
        op.create_table(
            "user_risk_state",
            sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("current_drawdown_pct", sa.Numeric(precision=10, scale=4), nullable=False, server_default="0.0"),
            sa.Column("longest_losing_streak", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("current_losing_streak", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("longest_winning_streak", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("current_winning_streak", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("trades_last_24h", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("avg_exposure_pct", sa.Numeric(precision=10, scale=4), nullable=False, server_default="0.0"),
            sa.Column("last_updated", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    else:
        # SQLite fallback (use String for UUID)
        op.create_table(
            "user_risk_state",
            sa.Column("user_id", sa.String(36), primary_key=True),
            sa.Column("current_drawdown_pct", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("longest_losing_streak", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("current_losing_streak", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("longest_winning_streak", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("current_winning_streak", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("trades_last_24h", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("avg_exposure_pct", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("last_updated", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    
    op.create_index("ix_user_risk_state_last_updated", "user_risk_state", ["last_updated"])


def downgrade() -> None:
    op.drop_index("ix_user_risk_state_last_updated", table_name="user_risk_state")
    op.drop_table("user_risk_state")

