"""Add exposure ledger table for tracking positions and aggregate exposure.

Revision ID: 017_add_exposure_ledger
Revises: 016_add_ensemble_weights
Create Date: 2024-01-XX XX:XX:XX.XXXXXX

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = '017_add_exposure_ledger'
down_revision = '016_add_ensemble_weights'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if using PostgreSQL
    bind = op.get_bind()
    is_postgres = bind.dialect.name == 'postgresql'
    
    if is_postgres:
        # Create exposure_ledger table
        op.create_table(
            'exposure_ledger',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', UUID(as_uuid=True), nullable=False),
            sa.Column('recommendation_id', sa.Integer(), nullable=False),
            sa.Column('symbol', sa.String(length=16), nullable=False),
            sa.Column('direction', sa.String(length=8), nullable=False),
            sa.Column('notional', sa.Float(), nullable=False),
            sa.Column('beta_bucket', sa.String(length=16), nullable=False, server_default='high'),
            sa.Column('beta_value', sa.Float(), nullable=False, server_default='1.0'),
            sa.Column('entry_price', sa.Float(), nullable=False),
            sa.Column('opened_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['recommendation_id'], ['recommendations.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('user_id', 'recommendation_id', name='uq_exposure_ledger_user_recommendation')
        )
        
        # Create indexes
        op.create_index('ix_exposure_ledger_user_id', 'exposure_ledger', ['user_id'])
        op.create_index('ix_exposure_ledger_recommendation_id', 'exposure_ledger', ['recommendation_id'])
        op.create_index('ix_exposure_ledger_symbol', 'exposure_ledger', ['symbol'])
        op.create_index('ix_exposure_ledger_opened_at', 'exposure_ledger', ['opened_at'])
        op.create_index('ix_exposure_ledger_closed_at', 'exposure_ledger', ['closed_at'])
        op.create_index('ix_exposure_ledger_is_active', 'exposure_ledger', ['is_active'])
    else:
        # SQLite fallback
        op.create_table(
            'exposure_ledger',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.String(length=36), nullable=False),  # UUID as string for SQLite
            sa.Column('recommendation_id', sa.Integer(), nullable=False),
            sa.Column('symbol', sa.String(length=16), nullable=False),
            sa.Column('direction', sa.String(length=8), nullable=False),
            sa.Column('notional', sa.Float(), nullable=False),
            sa.Column('beta_bucket', sa.String(length=16), nullable=False, server_default='high'),
            sa.Column('beta_value', sa.Float(), nullable=False, server_default='1.0'),
            sa.Column('entry_price', sa.Float(), nullable=False),
            sa.Column('opened_at', sa.DateTime(), nullable=False),
            sa.Column('closed_at', sa.DateTime(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['recommendation_id'], ['recommendations.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('user_id', 'recommendation_id', name='uq_exposure_ledger_user_recommendation')
        )
        
        # Create indexes for SQLite
        op.create_index('ix_exposure_ledger_user_id', 'exposure_ledger', ['user_id'])
        op.create_index('ix_exposure_ledger_recommendation_id', 'exposure_ledger', ['recommendation_id'])
        op.create_index('ix_exposure_ledger_symbol', 'exposure_ledger', ['symbol'])
        op.create_index('ix_exposure_ledger_opened_at', 'exposure_ledger', ['opened_at'])
        op.create_index('ix_exposure_ledger_closed_at', 'exposure_ledger', ['closed_at'])
        op.create_index('ix_exposure_ledger_is_active', 'exposure_ledger', ['is_active'])


def downgrade() -> None:
    op.drop_index('ix_exposure_ledger_is_active', table_name='exposure_ledger')
    op.drop_index('ix_exposure_ledger_closed_at', table_name='exposure_ledger')
    op.drop_index('ix_exposure_ledger_opened_at', table_name='exposure_ledger')
    op.drop_index('ix_exposure_ledger_symbol', table_name='exposure_ledger')
    op.drop_index('ix_exposure_ledger_recommendation_id', table_name='exposure_ledger')
    op.drop_index('ix_exposure_ledger_user_id', table_name='exposure_ledger')
    op.drop_table('exposure_ledger')

