"""Add cost tracking tables.

Revision ID: 002
Revises: 001
Create Date: 2026-01-20 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create cost_transactions table
    op.create_table(
        "cost_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", sa.String(128), nullable=True),
        sa.Column(
            "cost_type",
            sa.Enum("EMBEDDING", "TOC_DETECTION", "IMAGE_SUMMARY", "RAG_QUERY", name="costtype"),
            nullable=False,
        ),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=8), nullable=False),
        sa.Column("cost_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    
    # Create indexes for efficient querying
    op.create_index("ix_cost_transactions_document_id", "cost_transactions", ["document_id"])
    op.create_index("ix_cost_transactions_user_id", "cost_transactions", ["user_id"])
    op.create_index("ix_cost_transactions_cost_type", "cost_transactions", ["cost_type"])
    op.create_index("ix_cost_transactions_created_at", "cost_transactions", ["created_at"])
    
    # Create cost_summaries table for aggregated data
    op.create_table(
        "cost_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("summary_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(128), nullable=True),
        sa.Column("embedding_cost", sa.Numeric(precision=12, scale=8), nullable=False, server_default="0"),
        sa.Column("toc_detection_cost", sa.Numeric(precision=12, scale=8), nullable=False, server_default="0"),
        sa.Column("image_summary_cost", sa.Numeric(precision=12, scale=8), nullable=False, server_default="0"),
        sa.Column("rag_query_cost", sa.Numeric(precision=12, scale=8), nullable=False, server_default="0"),
        sa.Column("total_cost", sa.Numeric(precision=12, scale=8), nullable=False, server_default="0"),
        sa.Column("total_input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("transaction_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    
    op.create_index("ix_cost_summaries_summary_date", "cost_summaries", ["summary_date"])
    op.create_index("ix_cost_summaries_user_id", "cost_summaries", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_cost_summaries_user_id", table_name="cost_summaries")
    op.drop_index("ix_cost_summaries_summary_date", table_name="cost_summaries")
    op.drop_table("cost_summaries")
    
    op.drop_index("ix_cost_transactions_created_at", table_name="cost_transactions")
    op.drop_index("ix_cost_transactions_cost_type", table_name="cost_transactions")
    op.drop_index("ix_cost_transactions_user_id", table_name="cost_transactions")
    op.drop_index("ix_cost_transactions_document_id", table_name="cost_transactions")
    op.drop_table("cost_transactions")
    
    # Drop enum
    op.execute("DROP TYPE IF EXISTS costtype")
