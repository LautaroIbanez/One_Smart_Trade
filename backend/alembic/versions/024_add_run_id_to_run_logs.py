"""Add run_id and outcome_details to run_logs for deterministic pipeline tracking.

Revision ID: 024
Revises: 023
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    # Add run_id column to run_logs table
    op.add_column("run_logs", sa.Column("run_id", sa.String(length=128), nullable=True))
    
    # Add outcome_details JSON column to run_logs table
    op.add_column("run_logs", sa.Column("outcome_details", sa.JSON(), nullable=True))
    
    # Create index for run_id
    op.create_index(op.f("ix_run_logs_run_id"), "run_logs", ["run_id"], unique=False)


def downgrade() -> None:
    # Drop index
    op.drop_index(op.f("ix_run_logs_run_id"), table_name="run_logs")
    
    # Drop columns
    op.drop_column("run_logs", "outcome_details")
    op.drop_column("run_logs", "run_id")

