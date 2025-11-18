"""Add exported_by field to exports_audit table.

Revision ID: 018
Revises: 017
Create Date: 2024-11-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '018'
down_revision = '017'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add exported_by column to exports_audit table
    op.add_column('exports_audit', sa.Column('exported_by', sa.String(length=128), nullable=True, server_default='anonymous'))
    op.create_index(op.f('ix_exports_audit_exported_by'), 'exports_audit', ['exported_by'], unique=False)


def downgrade() -> None:
    # Drop index and column
    op.drop_index(op.f('ix_exports_audit_exported_by'), table_name='exports_audit')
    op.drop_column('exports_audit', 'exported_by')

