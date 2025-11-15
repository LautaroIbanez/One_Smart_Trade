"""Add traceability fields to recommendations and exports audit table.

Revision ID: 008
Revises: 007
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add traceability fields to recommendations
    op.add_column('recommendations', sa.Column('code_commit', sa.String(length=64), nullable=True))
    op.add_column('recommendations', sa.Column('dataset_version', sa.String(length=128), nullable=True))
    op.add_column('recommendations', sa.Column('params_digest', sa.String(length=64), nullable=True))
    op.add_column('recommendations', sa.Column('snapshot_json', sa.JSON(), nullable=True))

    # Create indexes for traceability fields
    op.create_index(op.f('ix_recommendations_code_commit'), 'recommendations', ['code_commit'], unique=False)
    op.create_index(op.f('ix_recommendations_dataset_version'), 'recommendations', ['dataset_version'], unique=False)
    op.create_index(op.f('ix_recommendations_params_digest'), 'recommendations', ['params_digest'], unique=False)

    # Create exports_audit table
    op.create_table(
        'exports_audit',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.Column('filters', sa.JSON(), nullable=True),
        sa.Column('format', sa.String(length=16), nullable=False),
        sa.Column('record_count', sa.Integer(), nullable=False),
        sa.Column('file_hash', sa.String(length=64), nullable=False),
        sa.Column('file_size_bytes', sa.Integer(), nullable=False),
        sa.Column('export_params', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_exports_audit_timestamp'), 'exports_audit', ['timestamp'], unique=False)
    op.create_index(op.f('ix_exports_audit_created_at'), 'exports_audit', ['created_at'], unique=False)


def downgrade() -> None:
    # Drop exports_audit table
    op.drop_index(op.f('ix_exports_audit_created_at'), table_name='exports_audit')
    op.drop_index(op.f('ix_exports_audit_timestamp'), table_name='exports_audit')
    op.drop_table('exports_audit')

    # Drop indexes
    op.drop_index(op.f('ix_recommendations_params_digest'), table_name='recommendations')
    op.drop_index(op.f('ix_recommendations_dataset_version'), table_name='recommendations')
    op.drop_index(op.f('ix_recommendations_code_commit'), table_name='recommendations')

    # Drop columns
    op.drop_column('recommendations', 'snapshot_json')
    op.drop_column('recommendations', 'params_digest')
    op.drop_column('recommendations', 'dataset_version')
    op.drop_column('recommendations', 'code_commit')


