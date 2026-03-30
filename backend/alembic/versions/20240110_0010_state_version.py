"""Add state_version for optimistic locking on learning_states.

Revision ID: 0010
Revises: 0009
Create Date: 2024-01-10

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'learning_states',
        sa.Column('state_version', sa.Integer(), server_default='0', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('learning_states', 'state_version')
