"""Add backtest metrics fields to recommendations for KPI tracking.

Revision ID: 026
Revises: 025
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "026"
down_revision: Union[str, None] = "025"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    # Add backtest metrics columns to recommendations table
    op.add_column("recommendations", sa.Column("backtest_cagr", sa.Float(), nullable=True))
    op.add_column("recommendations", sa.Column("backtest_win_rate", sa.Float(), nullable=True))
    op.add_column("recommendations", sa.Column("backtest_risk_reward_ratio", sa.Float(), nullable=True))
    op.add_column("recommendations", sa.Column("backtest_max_drawdown", sa.Float(), nullable=True))
    op.add_column("recommendations", sa.Column("backtest_slippage_bps", sa.Float(), nullable=True))


def downgrade() -> None:
    # Drop columns
    op.drop_column("recommendations", "backtest_slippage_bps")
    op.drop_column("recommendations", "backtest_max_drawdown")
    op.drop_column("recommendations", "backtest_risk_reward_ratio")
    op.drop_column("recommendations", "backtest_win_rate")
    op.drop_column("recommendations", "backtest_cagr")

