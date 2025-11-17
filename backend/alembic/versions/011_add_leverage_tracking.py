"""Add leverage tracking to user_risk_state and leverage_alerts table.

Revision ID: 011
Revises: 010
Create Date: 2024-01-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if using PostgreSQL
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    
    # Add leverage fields to user_risk_state
    op.add_column("user_risk_state", sa.Column("current_equity", sa.Numeric(precision=15, scale=4) if is_postgres else sa.Float(), nullable=False, server_default="0.0"))
    op.add_column("user_risk_state", sa.Column("total_notional", sa.Numeric(precision=15, scale=4) if is_postgres else sa.Float(), nullable=False, server_default="0.0"))
    op.add_column("user_risk_state", sa.Column("effective_leverage", sa.Numeric(precision=10, scale=4) if is_postgres else sa.Float(), nullable=False, server_default="0.0"))
    op.add_column("user_risk_state", sa.Column("leverage_hard_stop", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("user_risk_state", sa.Column("leverage_hard_stop_since", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_user_risk_state_leverage_hard_stop", "user_risk_state", ["leverage_hard_stop"])
    
    # Create leverage_alerts table
    if is_postgres:
        from sqlalchemy.dialects import postgresql
        op.create_table(
            "leverage_alerts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("leverage", sa.Numeric(precision=10, scale=4), nullable=False),
            sa.Column("equity", sa.Numeric(precision=15, scale=4), nullable=False),
            sa.Column("notional", sa.Numeric(precision=15, scale=4), nullable=False),
            sa.Column("threshold", sa.Numeric(precision=10, scale=4), nullable=False),
            sa.Column("alert_type", sa.String(32), nullable=False),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    else:
        # SQLite fallback
        op.create_table(
            "leverage_alerts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("triggered_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("leverage", sa.Float(), nullable=False),
            sa.Column("equity", sa.Float(), nullable=False),
            sa.Column("notional", sa.Float(), nullable=False),
            sa.Column("threshold", sa.Float(), nullable=False),
            sa.Column("alert_type", sa.String(32), nullable=False),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    
    op.create_index("ix_leverage_alerts_user_id", "leverage_alerts", ["user_id"])
    op.create_index("ix_leverage_alerts_triggered_at", "leverage_alerts", ["triggered_at"])
    op.create_index("ix_leverage_alerts_created_at", "leverage_alerts", ["created_at"])
    op.create_index("ix_leverage_alerts_alert_type", "leverage_alerts", ["alert_type"])


def downgrade() -> None:
    op.drop_index("ix_leverage_alerts_alert_type", table_name="leverage_alerts")
    op.drop_index("ix_leverage_alerts_created_at", table_name="leverage_alerts")
    op.drop_index("ix_leverage_alerts_triggered_at", table_name="leverage_alerts")
    op.drop_index("ix_leverage_alerts_user_id", table_name="leverage_alerts")
    op.drop_table("leverage_alerts")
    op.drop_index("ix_user_risk_state_leverage_hard_stop", table_name="user_risk_state")
    op.drop_column("user_risk_state", "leverage_hard_stop_since")
    op.drop_column("user_risk_state", "leverage_hard_stop")
    op.drop_column("user_risk_state", "effective_leverage")
    op.drop_column("user_risk_state", "total_notional")
    op.drop_column("user_risk_state", "current_equity")



