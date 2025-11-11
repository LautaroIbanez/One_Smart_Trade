"""Add trade state fields to recommendations."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("recommendations") as batch_op:
        batch_op.add_column(sa.Column("status", sa.String(length=16), nullable=False, server_default="closed"))
        batch_op.add_column(sa.Column("opened_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("closed_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("exit_reason", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("exit_price", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("exit_price_pct", sa.Float(), nullable=True))
        batch_op.create_index("ix_recommendations_status", ["status"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("recommendations") as batch_op:
        batch_op.drop_index("ix_recommendations_status")
        batch_op.drop_column("exit_price_pct")
        batch_op.drop_column("exit_price")
        batch_op.drop_column("exit_reason")
        batch_op.drop_column("closed_at")
        batch_op.drop_column("opened_at")
        batch_op.drop_column("status")

