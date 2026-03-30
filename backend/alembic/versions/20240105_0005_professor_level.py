"""Add professor_level to learning_configs

Revision ID: 0005
Revises: 0004
Create Date: 2026-01-21

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add professor_level column to learning_configs table
    op.add_column(
        'learning_configs',
        sa.Column(
            'professor_level',
            sa.String(50),
            nullable=False,
            server_default='intermediate'
        )
    )


def downgrade() -> None:
    # Remove professor_level column
    op.drop_column('learning_configs', 'professor_level')
