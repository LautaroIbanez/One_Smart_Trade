"""Add ensemble weights table.

Revision ID: 016_add_ensemble_weights
Revises: 015_add_confidence_calibrated
Create Date: 2025-01-XX XX:XX:XX.XXXXXX

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '016_add_ensemble_weights'
down_revision: Union[str, None] = '015_add_confidence_calibrated'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create ensemble_weights table
    op.create_table(
        'ensemble_weights',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('regime', sa.String(length=32), nullable=False),
        sa.Column('strategy_name', sa.String(length=64), nullable=False),
        sa.Column('weight', sa.Float(), nullable=False),
        sa.Column('snapshot_date', sa.String(length=10), nullable=False),
        sa.Column('metrics', sa.JSON(), nullable=True),
        sa.Column('calculated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('regime', 'strategy_name', 'snapshot_date', name='uq_ensemble_weights_regime_strategy_date')
    )
    op.create_index(op.f('ix_ensemble_weights_regime'), 'ensemble_weights', ['regime'], unique=False)
    op.create_index(op.f('ix_ensemble_weights_strategy_name'), 'ensemble_weights', ['strategy_name'], unique=False)
    op.create_index(op.f('ix_ensemble_weights_snapshot_date'), 'ensemble_weights', ['snapshot_date'], unique=False)
    op.create_index(op.f('ix_ensemble_weights_calculated_at'), 'ensemble_weights', ['calculated_at'], unique=False)
    op.create_index(op.f('ix_ensemble_weights_is_active'), 'ensemble_weights', ['is_active'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_ensemble_weights_is_active'), table_name='ensemble_weights')
    op.drop_index(op.f('ix_ensemble_weights_calculated_at'), table_name='ensemble_weights')
    op.drop_index(op.f('ix_ensemble_weights_snapshot_date'), table_name='ensemble_weights')
    op.drop_index(op.f('ix_ensemble_weights_strategy_name'), table_name='ensemble_weights')
    op.drop_index(op.f('ix_ensemble_weights_regime'), table_name='ensemble_weights')
    op.drop_table('ensemble_weights')

