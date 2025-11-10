"""Add signal_breakdown column to recommendations

Revision ID: 003
Revises: 002
Create Date: 2025-11-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recommendations",
        sa.Column("signal_breakdown", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("recommendations", "signal_breakdown")


