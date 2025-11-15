"""Add knowledge base and user readings tables.

Revision ID: 012
Revises: 011
Create Date: 2024-01-18 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if using PostgreSQL
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    
    # Create knowledge_articles table
    if is_postgres:
        from sqlalchemy.dialects import postgresql
        op.create_table(
            "knowledge_articles",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("slug", sa.String(255), nullable=False, unique=True),
            sa.Column("category", sa.String(64), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("summary", sa.String(500), nullable=True),
            sa.Column("tags", postgresql.JSON, nullable=False, server_default="[]"),
            sa.Column("trigger_conditions", postgresql.JSON, nullable=True),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("pdf_path", sa.String(512), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_knowledge_articles_slug", "knowledge_articles", ["slug"], unique=True)
        op.create_index("ix_knowledge_articles_category", "knowledge_articles", ["category"])
        op.create_index("ix_knowledge_articles_is_active", "knowledge_articles", ["is_active"])
        op.create_index("ix_knowledge_articles_created_at", "knowledge_articles", ["created_at"])
    else:
        # SQLite fallback
        op.create_table(
            "knowledge_articles",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("slug", sa.String(255), nullable=False, unique=True),
            sa.Column("category", sa.String(64), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("summary", sa.String(500), nullable=True),
            sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("trigger_conditions", sa.JSON(), nullable=True),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("pdf_path", sa.String(512), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_knowledge_articles_slug", "knowledge_articles", ["slug"], unique=True)
        op.create_index("ix_knowledge_articles_category", "knowledge_articles", ["category"])
        op.create_index("ix_knowledge_articles_is_active", "knowledge_articles", ["is_active"])
        op.create_index("ix_knowledge_articles_created_at", "knowledge_articles", ["created_at"])
    
    # Create user_readings table
    if is_postgres:
        from sqlalchemy.dialects import postgresql
        op.create_table(
            "user_readings",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("article_id", sa.Integer(), nullable=False),
            sa.Column("first_read_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("read_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("pdf_downloaded", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("pdf_downloaded_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("user_id", "article_id", name="uq_user_readings_user_article"),
        )
    else:
        # SQLite fallback
        op.create_table(
            "user_readings",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("article_id", sa.Integer(), nullable=False),
            sa.Column("first_read_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("last_read_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("read_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("pdf_downloaded", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("pdf_downloaded_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("user_id", "article_id", name="uq_user_readings_user_article"),
        )
    
    op.create_index("ix_user_readings_user_id", "user_readings", ["user_id"])
    op.create_index("ix_user_readings_article_id", "user_readings", ["article_id"])
    op.create_index("ix_user_readings_first_read_at", "user_readings", ["first_read_at"])
    op.create_index("ix_user_readings_last_read_at", "user_readings", ["last_read_at"])


def downgrade() -> None:
    op.drop_index("ix_user_readings_last_read_at", table_name="user_readings")
    op.drop_index("ix_user_readings_first_read_at", table_name="user_readings")
    op.drop_index("ix_user_readings_article_id", table_name="user_readings")
    op.drop_index("ix_user_readings_user_id", table_name="user_readings")
    op.drop_table("user_readings")
    op.drop_index("ix_knowledge_articles_created_at", table_name="knowledge_articles")
    op.drop_index("ix_knowledge_articles_is_active", table_name="knowledge_articles")
    op.drop_index("ix_knowledge_articles_category", table_name="knowledge_articles")
    op.drop_index("ix_knowledge_articles_slug", table_name="knowledge_articles")
    op.drop_table("knowledge_articles")


