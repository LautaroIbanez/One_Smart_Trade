"""Add config_version field to recommendations for versioned signal configuration.

Revision ID: 023
Revises: 022
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    # Add config_version column to recommendations table
    # This stores a human-readable version identifier from the signal config
    op.add_column("recommendations", sa.Column("config_version", sa.String(length=64), nullable=True))
    
    # Create index for config_version
    op.create_index(op.f("ix_recommendations_config_version"), "recommendations", ["config_version"], unique=False)


def downgrade() -> None:
    # Drop index
    op.drop_index(op.f("ix_recommendations_config_version"), table_name="recommendations")
    
    # Drop column
    op.drop_column("recommendations", "config_version")

