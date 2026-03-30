"""Add freemium limits to user_subscriptions.

Revision ID: 0008
Revises: 0007
Create Date: 2024-01-08

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename columns using raw SQL (more reliable)
    op.execute("ALTER TABLE user_subscriptions RENAME COLUMN pdfs_used_this_month TO books_used_this_month")
    op.execute("ALTER TABLE user_subscriptions RENAME COLUMN monthly_pdf_limit TO monthly_book_limit")
    
    # Drop old max_books column if exists (from previous migration attempt)
    try:
        op.drop_column('user_subscriptions', 'max_books')
    except:
        pass

    op.add_column(
        'user_subscriptions',
        sa.Column('max_plan_days', sa.Integer(), nullable=True),
    )

    # Update limits based on tier
    op.execute("UPDATE user_subscriptions SET monthly_book_limit = 2 WHERE tier = 'free'")
    op.execute("UPDATE user_subscriptions SET monthly_book_limit = -1 WHERE tier = 'byok'")
    op.execute("UPDATE user_subscriptions SET max_plan_days = 30 WHERE tier = 'free'")
    op.execute("UPDATE user_subscriptions SET max_plan_days = 60 WHERE tier = 'byok'")
    op.execute("UPDATE user_subscriptions SET monthly_quiz_limit = 30 WHERE tier = 'free'")
    op.execute("UPDATE user_subscriptions SET monthly_quiz_limit = -1 WHERE tier = 'byok'")


def downgrade() -> None:
    op.drop_column('user_subscriptions', 'max_plan_days')
    op.execute("ALTER TABLE user_subscriptions RENAME COLUMN books_used_this_month TO pdfs_used_this_month")
    op.execute("ALTER TABLE user_subscriptions RENAME COLUMN monthly_book_limit TO monthly_pdf_limit")
