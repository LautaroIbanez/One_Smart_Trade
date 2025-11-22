"""Add spot metadata to recommendations

Revision ID: 004
Revises: 003
Create Date: 2025-11-08 12:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recommendations", sa.Column("market_timestamp", sa.String(length=32), nullable=True))
    op.add_column("recommendations", sa.Column("spot_source", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("recommendations", "spot_source")
    op.drop_column("recommendations", "market_timestamp")















