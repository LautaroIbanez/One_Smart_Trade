"""Add seed field to recommendations for deterministic Monte Carlo.

Revision ID: 022
Revises: 021
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    # Add seed column to recommendations table
    op.add_column("recommendations", sa.Column("seed", sa.Integer(), nullable=True))
    
    # Create index for seed
    op.create_index(op.f("ix_recommendations_seed"), "recommendations", ["seed"], unique=False)


def downgrade() -> None:
    # Drop index
    op.drop_index(op.f("ix_recommendations_seed"), table_name="recommendations")
    
    # Drop column
    op.drop_column("recommendations", "seed")

