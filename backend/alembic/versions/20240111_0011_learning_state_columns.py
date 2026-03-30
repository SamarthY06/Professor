"""Add day-tracking columns to learning_states.

Revision ID: 0011
Revises: 0010
Create Date: 2024-01-11

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'learning_states',
        sa.Column('current_day', sa.Integer(), server_default='1', nullable=False),
    )
    op.add_column(
        'learning_states',
        sa.Column(
            'completed_days',
            postgresql.ARRAY(sa.Integer()),
            server_default='{}',
            nullable=False,
        ),
    )
    op.add_column(
        'learning_states',
        sa.Column('plan_start_date', sa.Date(), nullable=True),
    )
    op.add_column(
        'learning_states',
        sa.Column('day_topics_covered', postgresql.ARRAY(sa.Text()), nullable=True),
    )
    op.add_column(
        'learning_states',
        sa.Column('current_day_scope_description', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('learning_states', 'current_day_scope_description')
    op.drop_column('learning_states', 'day_topics_covered')
    op.drop_column('learning_states', 'plan_start_date')
    op.drop_column('learning_states', 'completed_days')
    op.drop_column('learning_states', 'current_day')
