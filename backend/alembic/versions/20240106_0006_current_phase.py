"""Add current_phase field to learning_states.

Revision ID: 0006
Revises: 0005
Create Date: 2024-01-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add current_phase column with default value
    op.add_column(
        'learning_states',
        sa.Column('current_phase', sa.String(30), nullable=False, server_default='greeting')
    )


def downgrade() -> None:
    op.drop_column('learning_states', 'current_phase')
