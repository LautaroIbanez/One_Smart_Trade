"""Add backtest_run_id field to recommendations for mandatory backtesting validation.

Revision ID: 025
Revises: 024
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    # Add backtest_run_id column to recommendations table
    # This stores the run_id from the mandatory backtest validation
    op.add_column("recommendations", sa.Column("backtest_run_id", sa.String(length=128), nullable=True))
    
    # Create index for backtest_run_id
    op.create_index(op.f("ix_recommendations_backtest_run_id"), "recommendations", ["backtest_run_id"], unique=False)


def downgrade() -> None:
    # Drop index
    op.drop_index(op.f("ix_recommendations_backtest_run_id"), table_name="recommendations")
    
    # Drop column
    op.drop_column("recommendations", "backtest_run_id")

