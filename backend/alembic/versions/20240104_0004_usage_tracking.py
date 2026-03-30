"""Add usage tracking and subscription tables.

Revision ID: 0004
Revises: 0003
Create Date: 2024-01-04

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0004'
down_revision = '0003_learning_config'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # User subscriptions table
    op.create_table(
        'user_subscriptions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False),
        sa.Column('tier', sa.String(50), default='free', nullable=False),
        sa.Column('monthly_pdf_limit', sa.Integer(), default=5),
        sa.Column('monthly_message_limit', sa.Integer(), default=50),
        sa.Column('monthly_quiz_limit', sa.Integer(), default=10),
        sa.Column('pdfs_used_this_month', sa.Integer(), default=0),
        sa.Column('messages_used_this_month', sa.Integer(), default=0),
        sa.Column('quizzes_used_this_month', sa.Integer(), default=0),
        sa.Column('preferred_model', sa.String(100), nullable=True),
        sa.Column('use_batch_api', sa.Boolean(), default=False),
        sa.Column('billing_cycle_start', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_user_subscriptions_user_id', 'user_subscriptions', ['user_id'])
    op.create_index('ix_user_subscriptions_tier', 'user_subscriptions', ['tier'])

    # Usage logs table
    op.create_table(
        'usage_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('usage_type', sa.String(50), nullable=False),
        sa.Column('model_used', sa.String(100), nullable=False),
        sa.Column('input_tokens', sa.Integer(), default=0),
        sa.Column('output_tokens', sa.Integer(), default=0),
        sa.Column('cached_tokens', sa.Integer(), default=0),
        sa.Column('cost_cents', sa.Integer(), default=0),
        sa.Column('paid_by', sa.String(20), default='platform'),
        sa.Column('book_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('request_id', sa.String(100), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_usage_logs_user_id', 'usage_logs', ['user_id'])
    op.create_index('ix_usage_logs_usage_type', 'usage_logs', ['usage_type'])
    op.create_index('ix_usage_logs_created_at', 'usage_logs', ['created_at'])
    op.create_index('ix_usage_logs_paid_by', 'usage_logs', ['paid_by'])

    # Daily usage aggregates
    op.create_table(
        'daily_usage_aggregates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('date', sa.DateTime(), nullable=False),
        sa.Column('chat_messages', sa.Integer(), default=0),
        sa.Column('pdfs_uploaded', sa.Integer(), default=0),
        sa.Column('quizzes_taken', sa.Integer(), default=0),
        sa.Column('study_time_minutes', sa.Integer(), default=0),
        sa.Column('total_input_tokens', sa.Integer(), default=0),
        sa.Column('total_output_tokens', sa.Integer(), default=0),
        sa.Column('platform_cost_cents', sa.Integer(), default=0),
        sa.Column('user_cost_cents', sa.Integer(), default=0),
        sa.Column('model_usage', postgresql.JSONB(), nullable=True),
    )
    op.create_index('ix_daily_usage_aggregates_user_id', 'daily_usage_aggregates', ['user_id'])
    op.create_index('ix_daily_usage_aggregates_date', 'daily_usage_aggregates', ['date'])
    op.create_unique_constraint('uq_daily_usage_user_date', 'daily_usage_aggregates', ['user_id', 'date'])

    # Platform usage aggregates
    op.create_table(
        'platform_usage_aggregates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('date', sa.DateTime(), unique=True, nullable=False),
        sa.Column('total_users', sa.Integer(), default=0),
        sa.Column('new_users', sa.Integer(), default=0),
        sa.Column('active_users', sa.Integer(), default=0),
        sa.Column('free_tier_users', sa.Integer(), default=0),
        sa.Column('byok_users', sa.Integer(), default=0),
        sa.Column('pro_users', sa.Integer(), default=0),
        sa.Column('total_messages', sa.Integer(), default=0),
        sa.Column('total_pdfs', sa.Integer(), default=0),
        sa.Column('total_quizzes', sa.Integer(), default=0),
        sa.Column('total_input_tokens', sa.Integer(), default=0),
        sa.Column('total_output_tokens', sa.Integer(), default=0),
        sa.Column('platform_cost_cents', sa.Integer(), default=0),
        sa.Column('model_usage', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_platform_usage_aggregates_date', 'platform_usage_aggregates', ['date'])

    # Model pricing table
    op.create_table(
        'model_pricing',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('model_name', sa.String(100), unique=True, nullable=False),
        sa.Column('display_name', sa.String(100), nullable=False),
        sa.Column('input_price_per_million', sa.Integer(), nullable=False),
        sa.Column('output_price_per_million', sa.Integer(), nullable=False),
        sa.Column('cached_input_price_per_million', sa.Integer(), nullable=True),
        sa.Column('is_available', sa.Boolean(), default=True),
        sa.Column('supports_batch', sa.Boolean(), default=False),
        sa.Column('max_context_tokens', sa.Integer(), default=128000),
        sa.Column('available_for_free', sa.Boolean(), default=False),
        sa.Column('available_for_byok', sa.Boolean(), default=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )

    # User feedback table
    op.create_table(
        'user_feedback',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('feedback_type', sa.String(50), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(255), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('book_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('page_url', sa.String(500), nullable=True),
        sa.Column('status', sa.String(50), default='new'),
        sa.Column('admin_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_user_feedback_user_id', 'user_feedback', ['user_id'])
    op.create_index('ix_user_feedback_status', 'user_feedback', ['status'])
    op.create_index('ix_user_feedback_created_at', 'user_feedback', ['created_at'])

    # Insert default model pricing based on OpenAI's current pricing
    op.execute("""
        INSERT INTO model_pricing (id, model_name, display_name, input_price_per_million, output_price_per_million, cached_input_price_per_million, is_available, supports_batch, max_context_tokens, available_for_free, available_for_byok, description, created_at, updated_at)
        VALUES 
        (gen_random_uuid(), 'gpt-4o', 'GPT-4o', 250, 1000, 125, true, true, 128000, false, true, 'Most capable model for complex tasks', NOW(), NOW()),
        (gen_random_uuid(), 'gpt-4o-mini', 'GPT-4o Mini', 15, 60, 8, true, true, 128000, true, true, 'Fast and affordable for simple tasks', NOW(), NOW()),
        (gen_random_uuid(), 'gpt-5.2', 'GPT-5.2', 175, 1400, 18, true, true, 200000, false, true, 'Best model for coding and agentic tasks', NOW(), NOW()),
        (gen_random_uuid(), 'gpt-5.2-pro', 'GPT-5.2 Pro', 2100, 16800, null, true, false, 200000, false, true, 'Smartest and most precise model', NOW(), NOW()),
        (gen_random_uuid(), 'gpt-5-mini', 'GPT-5 Mini', 25, 200, 3, true, true, 200000, true, true, 'Faster, cheaper version of GPT-5', NOW(), NOW()),
        (gen_random_uuid(), 'text-embedding-3-small', 'Embedding Small', 2, 0, null, true, true, 8191, true, true, 'Efficient embeddings for RAG', NOW(), NOW()),
        (gen_random_uuid(), 'text-embedding-3-large', 'Embedding Large', 13, 0, null, true, true, 8191, false, true, 'High quality embeddings', NOW(), NOW())
    """)


def downgrade() -> None:
    op.drop_table('user_feedback')
    op.drop_table('model_pricing')
    op.drop_table('platform_usage_aggregates')
    op.drop_table('daily_usage_aggregates')
    op.drop_table('usage_logs')
    op.drop_table('user_subscriptions')
