"""Add spot metadata columns to recommendations table."""

from alembic import op
import sqlalchemy as sa

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



