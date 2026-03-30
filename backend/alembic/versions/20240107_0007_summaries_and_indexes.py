"""Add summaries fields and indexes for production.

Revision ID: 0007
Revises: 0006
Create Date: 2024-01-07

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add summary fields to learning_states
    op.add_column(
        'learning_states',
        sa.Column('day_summaries', postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.add_column(
        'learning_states',
        sa.Column('chapter_summaries', postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.add_column(
        'learning_states',
        sa.Column('cumulative_summary', sa.Text(), nullable=True)
    )
    
    # Add composite indexes for common queries
    op.create_index(
        'ix_chat_sessions_user_book_active',
        'chat_sessions',
        ['user_id', 'book_id', 'is_active'],
        unique=False
    )
    op.create_index(
        'ix_learning_states_user_book',
        'learning_states',
        ['user_id', 'book_id'],
        unique=False
    )
    op.create_index(
        'ix_chat_messages_session_created',
        'chat_messages',
        ['session_id', 'created_at'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_chat_messages_session_created', table_name='chat_messages')
    op.drop_index('ix_learning_states_user_book', table_name='learning_states')
    op.drop_index('ix_chat_sessions_user_book_active', table_name='chat_sessions')
    op.drop_column('learning_states', 'cumulative_summary')
    op.drop_column('learning_states', 'chapter_summaries')
    op.drop_column('learning_states', 'day_summaries')
