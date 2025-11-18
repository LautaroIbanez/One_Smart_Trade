"""Add knowledge engagement tracking and enhance knowledge articles.

Revision ID: 020
Revises: 019
Create Date: 2024-11-18 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    # Check if using PostgreSQL
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    
    # Add new columns to knowledge_articles
    op.add_column("knowledge_articles", sa.Column("download_url", sa.String(512), nullable=True))
    op.add_column("knowledge_articles", sa.Column("micro_habits", sa.JSON(), nullable=True))
    op.add_column("knowledge_articles", sa.Column("is_critical", sa.Boolean(), nullable=False, server_default="false"))
    op.create_index("ix_knowledge_articles_is_critical", "knowledge_articles", ["is_critical"])
    
    # Add new columns to user_readings
    op.add_column("user_readings", sa.Column("completed", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("user_readings", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_user_readings_completed", "user_readings", ["completed"])
    
    # Create knowledge_engagement table
    if is_postgres:
        from sqlalchemy.dialects import postgresql
        op.create_table(
            "knowledge_engagement",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("article_id", sa.Integer(), nullable=False),
            sa.Column("engagement_type", sa.String(32), nullable=False),
            sa.Column("metadata", postgresql.JSON, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    else:
        # SQLite fallback
        op.create_table(
            "knowledge_engagement",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("article_id", sa.Integer(), nullable=False),
            sa.Column("engagement_type", sa.String(32), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    
    op.create_index("ix_knowledge_engagement_user_id", "knowledge_engagement", ["user_id"])
    op.create_index("ix_knowledge_engagement_article_id", "knowledge_engagement", ["article_id"])
    op.create_index("ix_knowledge_engagement_engagement_type", "knowledge_engagement", ["engagement_type"])
    op.create_index("ix_knowledge_engagement_created_at", "knowledge_engagement", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_engagement_created_at", table_name="knowledge_engagement")
    op.drop_index("ix_knowledge_engagement_engagement_type", table_name="knowledge_engagement")
    op.drop_index("ix_knowledge_engagement_article_id", table_name="knowledge_engagement")
    op.drop_index("ix_knowledge_engagement_user_id", table_name="knowledge_engagement")
    op.drop_table("knowledge_engagement")
    op.drop_index("ix_user_readings_completed", table_name="user_readings")
    op.drop_column("user_readings", "completed_at")
    op.drop_column("user_readings", "completed")
    op.drop_index("ix_knowledge_articles_is_critical", table_name="knowledge_articles")
    op.drop_column("knowledge_articles", "is_critical")
    op.drop_column("knowledge_articles", "micro_habits")
    op.drop_column("knowledge_articles", "download_url")

