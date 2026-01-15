"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Required Environment Variables:
    - SECRET_KEY: JWT signing key (32+ chars)
    - ENCRYPTION_KEY: Fernet encryption key (32 bytes)
    - OPENAI_API_KEY: OpenAI API key for LLM operations
    - GOOGLE_CLIENT_ID: Google OAuth client ID
    - GOOGLE_CLIENT_SECRET: Google OAuth client secret
    
    Optional Environment Variables:
    - DATABASE_URL: PostgreSQL connection string
    - REDIS_URL: Redis connection string
    - TEMPORAL_HOST: Temporal server address
    """
    
    # Application
    app_name: str = "Professor MVP"
    environment: str = "development"
    debug: bool = True
    
    # Database
    database_url: str = "postgresql+asyncpg://professor:professor_dev_password@postgres:5432/professor"
    database_url_sync: str = "postgresql://professor:professor_dev_password@postgres:5432/professor"
    
    # Redis
    redis_url: str = "redis://redis:6379"
    redis_host: str = "redis"
    redis_port: int = 6379
    
    # Temporal
    temporal_host: str = "temporal:7233"
    temporal_port: int = 7233
    temporal_namespace: str = "default"
    temporal_task_queue: str = "professor-queue"
    
    # Security
    secret_key: str = "super_secret_key_change_in_production"
    jwt_secret_key: Optional[str] = None  # Alternative name for secret_key
    encryption_key: str = "encryption_key_32_bytes_long_!!!"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours
    refresh_token_expire_days: int = 7
    
    # Google OAuth
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    
    # URLs
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"
    
    # File Storage
    pdf_storage_path: str = "/app/data/pdfs"
    log_storage_path: str = "/app/data/logs"
    cache_storage_path: str = "/app/data/cache"
    max_file_size_mb: int = 50
    
    # OpenAI Configuration
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4.1"
    openai_model_mini: str = "gpt-4.1-mini"
    
    # RAG Settings
    chunk_size: int = 400  # tokens
    chunk_overlap: int = 50  # tokens
    embedding_model: str = "text-embedding-ada-002"
    embedding_dimensions: int = 1536
    retrieval_top_k: int = 8  # Number of chunks to retrieve
    
    # Teaching Settings
    max_context_tokens: int = 8000
    max_response_tokens: int = 600
    default_temperature: float = 0.7
    
    # Quiz Settings
    questions_per_quiz: int = 5
    quiz_passing_score: float = 0.7
    attention_question_min_interval: int = 5  # messages
    attention_question_max_interval: int = 12  # messages
    attention_question_probability: float = 0.3
    
    # Cache TTLs (seconds)
    cache_ttl_user_state: int = 3600  # 1 hour
    cache_ttl_chapter_chunks: int = 3600  # 1 hour
    cache_ttl_chapter_summary: int = 86400  # 24 hours
    cache_ttl_conversation: int = 1800  # 30 minutes
    cache_ttl_embeddings: int = 604800  # 7 days
    
    # Twilio/WhatsApp Configuration
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_whatsapp_number: str = "whatsapp:+14155238886"  # Twilio sandbox number
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore unknown env vars


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
