"""Add risk_audit table for risk validation audit trail.

Revision ID: 019
Revises: 018
Create Date: 2024-11-18 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    # Check if using PostgreSQL
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    
    # Create risk_audit table
    if is_postgres:
        from sqlalchemy.dialects import postgresql
        op.create_table(
            "risk_audit",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("audit_type", sa.String(32), nullable=False),
            sa.Column("reason", sa.String(512), nullable=False),
            sa.Column("recommendation_id", sa.Integer(), nullable=True),
            sa.Column("context_data", postgresql.JSON, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    else:
        # SQLite fallback
        op.create_table(
            "risk_audit",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("blocked_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("audit_type", sa.String(32), nullable=False),
            sa.Column("reason", sa.String(512), nullable=False),
            sa.Column("recommendation_id", sa.Integer(), nullable=True),
            sa.Column("context_data", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    
    op.create_index("ix_risk_audit_user_id", "risk_audit", ["user_id"])
    op.create_index("ix_risk_audit_blocked_at", "risk_audit", ["blocked_at"])
    op.create_index("ix_risk_audit_audit_type", "risk_audit", ["audit_type"])
    op.create_index("ix_risk_audit_recommendation_id", "risk_audit", ["recommendation_id"])
    op.create_index("ix_risk_audit_created_at", "risk_audit", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_risk_audit_created_at", table_name="risk_audit")
    op.drop_index("ix_risk_audit_recommendation_id", table_name="risk_audit")
    op.drop_index("ix_risk_audit_audit_type", table_name="risk_audit")
    op.drop_index("ix_risk_audit_blocked_at", table_name="risk_audit")
    op.drop_index("ix_risk_audit_user_id", table_name="risk_audit")
    op.drop_table("risk_audit")

