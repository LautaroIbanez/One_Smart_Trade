"""Add unique snapshot constraint to recommendations."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    # Remove duplicate snapshots, keeping the most recent per (date, market_timestamp)
    conn.execute(
        sa.text(
            """
            DELETE FROM recommendations
            WHERE id NOT IN (
                SELECT id FROM (
                    SELECT
                        id,
                        ROW_NUMBER() OVER (
                            PARTITION BY date, COALESCE(market_timestamp, '')
                            ORDER BY datetime(created_at) DESC, id DESC
                        ) AS rn
                    FROM recommendations
                ) WHERE rn = 1
            )
            """
        )
    )
    with op.batch_alter_table("recommendations") as batch_op:
        batch_op.create_unique_constraint(
            "uq_recommendations_date_market_timestamp",
            ["date", "market_timestamp"],
        )


def downgrade() -> None:
    with op.batch_alter_table("recommendations") as batch_op:
        batch_op.drop_constraint(
            "uq_recommendations_date_market_timestamp",
            type_="unique",
        )

