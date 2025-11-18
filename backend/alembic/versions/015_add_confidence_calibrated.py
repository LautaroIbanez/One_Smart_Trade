"""add confidence_calibrated column to recommendations

Revision ID: 015_add_confidence_calibrated
Revises: 014_add_signal_outcomes_table
Create Date: 2025-11-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "015_add_confidence_calibrated"
down_revision = "014_add_signal_outcomes_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recommendations", sa.Column("confidence_calibrated", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("recommendations", "confidence_calibrated")

