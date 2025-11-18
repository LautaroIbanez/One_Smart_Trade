"""Add ingestion_timestamp field to recommendations for dataset versioning.

Revision ID: 021
Revises: 020
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    # Add ingestion_timestamp column to recommendations table
    op.add_column("recommendations", sa.Column("ingestion_timestamp", sa.DateTime(), nullable=True))
    
    # Create index for ingestion_timestamp
    op.create_index(op.f("ix_recommendations_ingestion_timestamp"), "recommendations", ["ingestion_timestamp"], unique=False)


def downgrade() -> None:
    # Drop index
    op.drop_index(op.f("ix_recommendations_ingestion_timestamp"), table_name="recommendations")
    
    # Drop column
    op.drop_column("recommendations", "ingestion_timestamp")

