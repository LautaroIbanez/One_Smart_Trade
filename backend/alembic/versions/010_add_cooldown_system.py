"""Add cooldown system to user_risk_state and cooldown_events table.

Revision ID: 010
Revises: 009
Create Date: 2024-01-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if using PostgreSQL
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    
    # Add cooldown fields to user_risk_state
    op.add_column("user_risk_state", sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_risk_state", sa.Column("cooldown_reason", sa.String(128), nullable=True))
    op.create_index("ix_user_risk_state_cooldown_until", "user_risk_state", ["cooldown_until"])
    
    # Create cooldown_events table
    if is_postgres:
        from sqlalchemy.dialects import postgresql
        op.create_table(
            "cooldown_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=False),
            sa.Column("reason", sa.String(128), nullable=False),
            sa.Column("losing_streak", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("trades_last_24h", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("current_drawdown_pct", sa.Numeric(precision=10, scale=4), nullable=False, server_default="0.0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    else:
        # SQLite fallback
        op.create_table(
            "cooldown_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("triggered_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("cooldown_until", sa.DateTime(), nullable=False),
            sa.Column("reason", sa.String(128), nullable=False),
            sa.Column("losing_streak", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("trades_last_24h", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("current_drawdown_pct", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    
    op.create_index("ix_cooldown_events_user_id", "cooldown_events", ["user_id"])
    op.create_index("ix_cooldown_events_triggered_at", "cooldown_events", ["triggered_at"])
    op.create_index("ix_cooldown_events_created_at", "cooldown_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_cooldown_events_created_at", table_name="cooldown_events")
    op.drop_index("ix_cooldown_events_triggered_at", table_name="cooldown_events")
    op.drop_index("ix_cooldown_events_user_id", table_name="cooldown_events")
    op.drop_table("cooldown_events")
    op.drop_index("ix_user_risk_state_cooldown_until", table_name="user_risk_state")
    op.drop_column("user_risk_state", "cooldown_reason")
    op.drop_column("user_risk_state", "cooldown_until")




