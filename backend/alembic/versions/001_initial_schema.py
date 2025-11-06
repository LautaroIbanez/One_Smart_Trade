"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'recommendations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('date', sa.String(length=10), nullable=True),
        sa.Column('signal', sa.String(length=8), nullable=True),
        sa.Column('entry_min', sa.Float(), nullable=True),
        sa.Column('entry_max', sa.Float(), nullable=True),
        sa.Column('entry_optimal', sa.Float(), nullable=True),
        sa.Column('stop_loss', sa.Float(), nullable=True),
        sa.Column('take_profit', sa.Float(), nullable=True),
        sa.Column('stop_loss_pct', sa.Float(), nullable=True),
        sa.Column('take_profit_pct', sa.Float(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('current_price', sa.Float(), nullable=True),
        sa.Column('indicators', sa.JSON(), nullable=True),
        sa.Column('risk_metrics', sa.JSON(), nullable=True),
        sa.Column('factors', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_recommendations_date'), 'recommendations', ['date'], unique=False)
    
    op.create_table(
        'run_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_type', sa.String(length=32), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=True),
        sa.Column('message', sa.String(length=255), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table(
        'backtest_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('version', sa.String(length=20), nullable=True),
        sa.Column('start_date', sa.String(length=20), nullable=True),
        sa.Column('end_date', sa.String(length=20), nullable=True),
        sa.Column('metrics', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_backtest_results_version'), 'backtest_results', ['version'], unique=False)
    op.create_index(op.f('ix_backtest_results_created_at'), 'backtest_results', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_backtest_results_created_at'), table_name='backtest_results')
    op.drop_index(op.f('ix_backtest_results_version'), table_name='backtest_results')
    op.drop_table('backtest_results')
    op.drop_index(op.f('ix_recommendations_date'), table_name='recommendations')
    op.drop_table('run_logs')
    op.drop_table('recommendations')

