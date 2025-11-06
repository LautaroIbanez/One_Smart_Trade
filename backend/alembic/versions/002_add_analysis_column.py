"""Add analysis column to recommendations

Revision ID: 002
Revises: 001
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('recommendations', sa.Column('analysis', sa.String(length=2000), nullable=True, server_default=''))


def downgrade() -> None:
    op.drop_column('recommendations', 'analysis')

