"""Rename metadata columns to avoid SQLAlchemy conflict.

Revision ID: 0002
Revises: 0001
Create Date: 2024-01-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename metadata columns to avoid SQLAlchemy reserved attribute conflict
    op.alter_column('books', 'metadata', new_column_name='book_metadata')
    op.alter_column('document_chunks', 'metadata', new_column_name='chunk_metadata')
    op.alter_column('chat_messages', 'metadata', new_column_name='message_metadata')


def downgrade() -> None:
    op.alter_column('books', 'book_metadata', new_column_name='metadata')
    op.alter_column('document_chunks', 'chunk_metadata', new_column_name='metadata')
    op.alter_column('chat_messages', 'message_metadata', new_column_name='metadata')
