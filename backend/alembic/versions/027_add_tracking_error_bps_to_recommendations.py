"""Add tracking_error_bps field to recommendations for SL/TP achievability monitoring.

Revision ID: 027
Revises: 026
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "027"
down_revision: Union[str, None] = "026"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    # Add tracking_error_bps column to recommendations table
    op.add_column("recommendations", sa.Column("tracking_error_bps", sa.Float(), nullable=True))


def downgrade() -> None:
    # Drop column
    op.drop_column("recommendations", "tracking_error_bps")

