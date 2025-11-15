"""Add versioning fields to strategy_champions table."""
from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.add_column("strategy_champions", sa.Column("params_version", sa.String(length=64), nullable=True))
    op.create_index(op.f("ix_strategy_champions_params_version"), "strategy_champions", ["params_version"], unique=False)
    op.add_column("strategy_champions", sa.Column("trained_on_regime", sa.JSON(), nullable=True))
    op.add_column("strategy_champions", sa.Column("statistical_test", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("strategy_champions", "statistical_test")
    op.drop_column("strategy_champions", "trained_on_regime")
    op.drop_index(op.f("ix_strategy_champions_params_version"), table_name="strategy_champions")
    op.drop_column("strategy_champions", "params_version")


