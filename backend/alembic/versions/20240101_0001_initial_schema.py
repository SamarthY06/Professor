"""Initial database schema.

Revision ID: 0001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')
    
    # Users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('email', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('phone', sa.String(20), nullable=True),
        sa.Column('role', sa.String(20), server_default='student'),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()')),
    )
    
    # User auth (OAuth)
    op.create_table(
        'user_auth',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('provider_user_id', sa.String(255), nullable=False),
        sa.Column('access_token_hash', sa.String(255), nullable=True),
        sa.Column('refresh_token_hash', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()')),
        sa.UniqueConstraint('provider', 'provider_user_id', name='uq_user_auth_provider'),
    )
    
    # Encrypted API keys
    op.create_table(
        'encrypted_api_keys',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False),
        sa.Column('encrypted_key', sa.LargeBinary, nullable=False),
        sa.Column('key_iv', sa.LargeBinary, nullable=False),
        sa.Column('key_hash', sa.String(64), nullable=False),
        sa.Column('is_valid', sa.Boolean, server_default='true'),
        sa.Column('last_validated_at', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()')),
    )
    
    # User sessions
    op.create_table(
        'user_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(255), nullable=False, index=True),
        sa.Column('device_info', postgresql.JSONB, nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('expires_at', sa.DateTime, nullable=False),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()')),
        sa.Column('last_active_at', sa.DateTime, server_default=sa.text('NOW()')),
    )
    
    # User settings
    op.create_table(
        'user_settings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False),
        sa.Column('professor_style', sa.String(50), server_default='balanced'),
        sa.Column('notification_preferences', postgresql.JSONB, server_default='{"email": true, "whatsapp": true}'),
        sa.Column('study_schedule', postgresql.JSONB, nullable=True),
        sa.Column('timezone', sa.String(50), server_default='UTC'),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()')),
    )
    
    # Books table
    op.create_table(
        'books',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('author', sa.String(255), nullable=True),
        sa.Column('file_path', sa.String(500), nullable=False),
        sa.Column('file_hash', sa.String(64), nullable=False, index=True),
        sa.Column('total_pages', sa.Integer, nullable=True),
        sa.Column('total_chapters', sa.Integer, nullable=True),
        sa.Column('processing_status', sa.String(50), server_default='pending'),
        sa.Column('processing_error', sa.Text, nullable=True),
        sa.Column('metadata', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()')),
    )
    
    # Book chapters
    op.create_table(
        'book_chapters',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('book_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('books.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('chapter_number', sa.Integer, nullable=False),
        sa.Column('title', sa.String(500), nullable=True),
        sa.Column('start_page', sa.Integer, nullable=True),
        sa.Column('end_page', sa.Integer, nullable=True),
        sa.Column('summary', sa.Text, nullable=True),
        sa.Column('key_concepts', postgresql.JSONB, nullable=True),
        sa.Column('prerequisite_chapters', postgresql.ARRAY(sa.Integer), nullable=True),
        sa.Column('estimated_duration_minutes', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()')),
        sa.UniqueConstraint('book_id', 'chapter_number', name='uq_book_chapter'),
    )
    
    # Goals table
    op.create_table(
        'goals',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('duration_days', sa.Integer, nullable=False),
        sa.Column('difficulty_level', sa.String(20), server_default='intermediate'),
        sa.Column('status', sa.String(50), server_default='active'),
        sa.Column('ai_generated_curriculum', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()')),
    )
    
    # Goal chapters
    op.create_table(
        'goal_chapters',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('goal_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('goals.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('week_number', sa.Integer, nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('topics', postgresql.JSONB, nullable=False),
        sa.Column('learning_objectives', postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column('summary', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()')),
        sa.UniqueConstraint('goal_id', 'week_number', name='uq_goal_week'),
    )
    
    # Learning states
    op.create_table(
        'learning_states',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('book_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('books.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('goal_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('goals.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('current_chapter', sa.Integer, server_default='1'),
        sa.Column('current_section', sa.String(255), nullable=True),
        sa.Column('completed_chapters', postgresql.ARRAY(sa.Integer), server_default='{}'),
        sa.Column('completed_sections', postgresql.JSONB, server_default='{}'),
        sa.Column('summarized_past_context', sa.Text, nullable=True),
        sa.Column('last_topic_discussed', sa.String(500), nullable=True),
        sa.Column('pending_topics', postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column('learning_plan', postgresql.JSONB, nullable=True),
        sa.Column('strict_mode', sa.Boolean, server_default='true'),
        sa.Column('professor_level', sa.String(20), server_default='intermediate'),
        sa.Column('motivation_score', sa.Float, server_default='1.0'),
        sa.Column('attention_score', sa.Float, server_default='1.0'),
        sa.Column('comprehension_score', sa.Float, server_default='1.0'),
        sa.Column('missed_sessions', sa.Integer, server_default='0'),
        sa.Column('total_study_time_minutes', sa.Integer, server_default='0'),
        sa.Column('last_session_summary', sa.Text, nullable=True),
        sa.Column('last_active_at', sa.DateTime, nullable=True),
        sa.Column('quiz_mode', sa.String(20), server_default='none'),
        sa.Column('pending_quiz_questions', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()')),
        sa.CheckConstraint(
            '(book_id IS NOT NULL AND goal_id IS NULL) OR (book_id IS NULL AND goal_id IS NOT NULL)',
            name='one_learning_target'
        ),
    )
    
    # Progress snapshots
    op.create_table(
        'progress_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('learning_state_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('learning_states.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('snapshot_date', sa.Date, nullable=False),
        sa.Column('chapter_progress', sa.Integer, nullable=True),
        sa.Column('quiz_scores', postgresql.JSONB, nullable=True),
        sa.Column('study_duration_minutes', sa.Integer, nullable=True),
        sa.Column('topics_covered', postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()')),
    )
    
    # Document chunks with vector embeddings
    op.create_table(
        'document_chunks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('book_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('books.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('chapter_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('book_chapters.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('section_title', sa.String(500), nullable=True),
        sa.Column('chunk_index', sa.Integer, nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False, index=True),
        sa.Column('token_count', sa.Integer, nullable=False),
        sa.Column('embedding', Vector(1536), nullable=True),
        sa.Column('metadata', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()')),
    )
    
    # Create vector index
    op.execute(
        'CREATE INDEX idx_document_chunks_embedding ON document_chunks '
        'USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)'
    )
    
    # Chapter summaries
    op.create_table(
        'chapter_summaries',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('book_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('books.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('chapter_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('book_chapters.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('summary_type', sa.String(50), nullable=False),
        sa.Column('summary_text', sa.Text, nullable=False),
        sa.Column('key_concepts', postgresql.JSONB, nullable=True),
        sa.Column('token_count', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()')),
        sa.UniqueConstraint('user_id', 'chapter_id', 'summary_type', name='uq_chapter_summary'),
    )
    
    # Topic relationships
    op.create_table(
        'topic_relationships',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('book_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('books.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('source_chapter_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('book_chapters.id'), nullable=True),
        sa.Column('target_chapter_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('book_chapters.id'), nullable=True),
        sa.Column('topic', sa.String(255), nullable=False),
        sa.Column('relationship_type', sa.String(50), nullable=True),
        sa.Column('strength', sa.Float, server_default='0.5'),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()')),
    )
    
    # Chat sessions
    op.create_table(
        'chat_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('learning_state_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('learning_states.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('book_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('books.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('goal_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('goals.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('chapter_context', sa.Integer, nullable=True),
        sa.Column('session_type', sa.String(50), server_default='learning'),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('message_count', sa.Integer, server_default='0'),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()')),
        sa.Column('last_message_at', sa.DateTime, nullable=True),
    )
    
    # Chat messages
    op.create_table(
        'chat_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('chat_sessions.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('agent_name', sa.String(50), nullable=True),
        sa.Column('agent_reasoning', sa.Text, nullable=True),
        sa.Column('context_used', postgresql.JSONB, nullable=True),
        sa.Column('chapter_at_time', sa.Integer, nullable=True),
        sa.Column('is_quiz_question', sa.Boolean, server_default='false'),
        sa.Column('quiz_answer_correct', sa.Boolean, nullable=True),
        sa.Column('token_count', sa.Integer, nullable=True),
        sa.Column('latency_ms', sa.Integer, nullable=True),
        sa.Column('metadata', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()')),
    )
    
    # Agent logs
    op.create_table(
        'agent_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True, index=True),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('chat_sessions.id'), nullable=True, index=True),
        sa.Column('book_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('chapter_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('agent_name', sa.String(50), nullable=False, index=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('input_data', postgresql.JSONB, nullable=True),
        sa.Column('output_data', postgresql.JSONB, nullable=True),
        sa.Column('state_before', postgresql.JSONB, nullable=True),
        sa.Column('state_after', postgresql.JSONB, nullable=True),
        sa.Column('execution_time_ms', sa.Integer, nullable=True),
        sa.Column('error', sa.Text, nullable=True),
        sa.Column('timestamp', sa.DateTime, server_default=sa.text('NOW()'), index=True),
    )
    
    # Quizzes
    op.create_table(
        'quizzes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('book_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('books.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('chapter_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('book_chapters.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('quiz_type', sa.String(50), nullable=False),
        sa.Column('title', sa.String(255), nullable=True),
        sa.Column('total_questions', sa.Integer, nullable=True),
        sa.Column('passing_score', sa.Float, server_default='0.7'),
        sa.Column('time_limit_minutes', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()')),
    )
    
    # Quiz questions
    op.create_table(
        'quiz_questions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('quiz_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('quizzes.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('book_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('books.id'), nullable=True),
        sa.Column('chapter_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('book_chapters.id'), nullable=True),
        sa.Column('question_text', sa.Text, nullable=False),
        sa.Column('question_type', sa.String(50), nullable=False),
        sa.Column('options', postgresql.JSONB, nullable=True),
        sa.Column('correct_answer', sa.Text, nullable=False),
        sa.Column('explanation', sa.Text, nullable=True),
        sa.Column('difficulty', sa.String(20), server_default='medium'),
        sa.Column('topic', sa.String(255), nullable=True),
        sa.Column('source_chunk_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('document_chunks.id'), nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()')),
    )
    
    # Quiz attempts
    op.create_table(
        'quiz_attempts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('quiz_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('quizzes.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('learning_state_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('learning_states.id'), nullable=True),
        sa.Column('started_at', sa.DateTime, server_default=sa.text('NOW()')),
        sa.Column('completed_at', sa.DateTime, nullable=True),
        sa.Column('score', sa.Float, nullable=True),
        sa.Column('passed', sa.Boolean, nullable=True),
        sa.Column('time_taken_seconds', sa.Integer, nullable=True),
        sa.Column('answers', postgresql.JSONB, nullable=True),
        sa.Column('feedback', postgresql.JSONB, nullable=True),
    )
    
    # Question responses
    op.create_table(
        'question_responses',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('attempt_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('quiz_attempts.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('question_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('quiz_questions.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_answer', sa.Text, nullable=True),
        sa.Column('is_correct', sa.Boolean, nullable=True),
        sa.Column('time_taken_seconds', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()')),
    )
    
    # Attention questions
    op.create_table(
        'attention_questions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('chat_sessions.id'), nullable=True, index=True),
        sa.Column('chapter_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('book_chapters.id'), nullable=True),
        sa.Column('question_text', sa.Text, nullable=False),
        sa.Column('expected_answer', sa.Text, nullable=True),
        sa.Column('user_answer', sa.Text, nullable=True),
        sa.Column('is_correct', sa.Boolean, nullable=True),
        sa.Column('asked_at', sa.DateTime, server_default=sa.text('NOW()')),
        sa.Column('answered_at', sa.DateTime, nullable=True),
        sa.Column('topic_being_taught', sa.String(255), nullable=True),
        sa.Column('triggered_by', sa.String(50), nullable=True),
    )
    
    # User notes
    op.create_table(
        'user_notes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('book_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('books.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('goal_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('goals.id', ondelete='SET NULL'), nullable=True),
        sa.Column('chapter_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('book_chapters.id', ondelete='SET NULL'), nullable=True),
        sa.Column('title', sa.String(255), nullable=True),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('source_message_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('chat_messages.id'), nullable=True),
        sa.Column('tags', postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column('is_pinned', sa.Boolean, server_default='false'),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()')),
    )
    
    # Reminders
    op.create_table(
        'reminders',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('learning_state_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('learning_states.id'), nullable=True),
        sa.Column('reminder_type', sa.String(50), nullable=False),
        sa.Column('channel', sa.String(50), nullable=False),
        sa.Column('message_template', sa.String(100), nullable=True),
        sa.Column('message_data', postgresql.JSONB, nullable=True),
        sa.Column('scheduled_at', sa.DateTime, nullable=False, index=True),
        sa.Column('sent_at', sa.DateTime, nullable=True),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('dedup_key', sa.String(255), nullable=True, index=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()')),
    )
    
    # Create unique index for reminder deduplication
    op.execute(
        "CREATE UNIQUE INDEX idx_reminder_dedup ON reminders(dedup_key) WHERE status = 'pending'"
    )
    
    # Admin logs
    op.create_table(
        'admin_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('admin_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True, index=True),
        sa.Column('action', sa.String(100), nullable=False, index=True),
        sa.Column('target_type', sa.String(50), nullable=True),
        sa.Column('target_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('details', postgresql.JSONB, nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), index=True),
    )
    
    # System metrics
    op.create_table(
        'system_metrics',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('metric_name', sa.String(100), nullable=False, index=True),
        sa.Column('metric_value', sa.Float, nullable=False),
        sa.Column('dimensions', postgresql.JSONB, nullable=True),
        sa.Column('recorded_at', sa.DateTime, server_default=sa.text('NOW()'), index=True),
    )
    
    # Feature flags
    op.create_table(
        'feature_flags',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('flag_name', sa.String(100), unique=True, nullable=False, index=True),
        sa.Column('is_enabled', sa.Boolean, server_default='false'),
        sa.Column('rollout_percentage', sa.Integer, server_default='0'),
        sa.Column('conditions', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()')),
    )


def downgrade() -> None:
    # Drop tables in reverse order due to foreign key constraints
    op.drop_table('feature_flags')
    op.drop_table('system_metrics')
    op.drop_table('admin_logs')
    op.execute('DROP INDEX IF EXISTS idx_reminder_dedup')
    op.drop_table('reminders')
    op.drop_table('user_notes')
    op.drop_table('attention_questions')
    op.drop_table('question_responses')
    op.drop_table('quiz_attempts')
    op.drop_table('quiz_questions')
    op.drop_table('quizzes')
    op.drop_table('agent_logs')
    op.drop_table('chat_messages')
    op.drop_table('chat_sessions')
    op.drop_table('topic_relationships')
    op.drop_table('chapter_summaries')
    op.execute('DROP INDEX IF EXISTS idx_document_chunks_embedding')
    op.drop_table('document_chunks')
    op.drop_table('progress_snapshots')
    op.drop_table('learning_states')
    op.drop_table('goal_chapters')
    op.drop_table('goals')
    op.drop_table('book_chapters')
    op.drop_table('books')
    op.drop_table('user_settings')
    op.drop_table('user_sessions')
    op.drop_table('encrypted_api_keys')
    op.drop_table('user_auth')
    op.drop_table('users')
