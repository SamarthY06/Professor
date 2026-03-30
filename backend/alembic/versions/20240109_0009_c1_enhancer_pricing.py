"""Add C1 Response Enhancer pricing table.

Revision ID: 0009
Revises: 0008
Create Date: 2024-01-09

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create c1_enhancer_pricing table
    op.create_table(
        'c1_enhancer_pricing',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('model_name', sa.String(100), unique=True, nullable=False),
        sa.Column('display_name', sa.String(100), nullable=False),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('input_price_per_million', sa.Integer(), nullable=False),
        sa.Column('output_price_per_million', sa.Integer(), nullable=False),
        sa.Column('is_available', sa.Boolean(), default=True),
        sa.Column('is_default', sa.Boolean(), default=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # Insert default C1 models with pricing from the guide
    op.execute("""
        INSERT INTO c1_enhancer_pricing (id, model_name, display_name, provider, input_price_per_million, output_price_per_million, is_available, is_default, description)
        VALUES 
        (gen_random_uuid(), 'c1/anthropic/claude-sonnet-4/v-20251230', 'Claude Sonnet 4', 'Anthropic', 300, 1500, true, true, 'Recommended model for response enhancement. Best quality for mathematical content.'),
        (gen_random_uuid(), 'c1/openai/gpt-5/v-20251230', 'GPT-5', 'OpenAI', 125, 1050, true, false, 'Alternative model for response enhancement. Good balance of cost and quality.')
    """)


def downgrade() -> None:
    op.drop_table('c1_enhancer_pricing')
