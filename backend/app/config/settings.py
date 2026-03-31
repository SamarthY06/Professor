"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
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
    
    # Security -- no hardcoded defaults; must be set via env vars
    secret_key: str = "CHANGE_ME_IN_PRODUCTION"
    jwt_secret_key: Optional[str] = None
    encryption_key: str = "CHANGE_ME_IN_PRODUCTION_32CHARS!"
    
    @property
    def effective_jwt_secret(self) -> str:
        """JWT signing key: uses jwt_secret_key if set, falls back to secret_key."""
        return self.jwt_secret_key or self.secret_key
    
    @model_validator(mode="after")
    def _validate_production_secrets(self):
        is_prod = self.environment in ("production", "staging")
        blocklist = ("CHANGE_ME", "super_secret", "changeme", "password")

        def _is_insecure(val: str) -> bool:
            return any(tok in val for tok in blocklist) or len(val) < 16

        if is_prod:
            if _is_insecure(self.secret_key):
                raise ValueError(
                    "SECRET_KEY must be a secure random string (>=16 chars) "
                    "in production/staging"
                )
            if _is_insecure(self.encryption_key) or len(self.encryption_key) < 32:
                raise ValueError(
                    "ENCRYPTION_KEY must be a secure random string (>=32 chars) "
                    "in production/staging"
                )
            if not self.jwt_secret_key or _is_insecure(self.jwt_secret_key):
                raise ValueError(
                    "JWT_SECRET_KEY must be set to a secure value "
                    "in production/staging"
                )
            if not self.openai_api_key:
                raise ValueError("OPENAI_API_KEY must be set in production/staging")
        return self
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
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
    
    # External RAG Service Configuration (Textbook_RAG on localhost:8001)
    rag_base_url: str
    rag_admin_username: str
    rag_admin_password: str
    rag_request_timeout: int = 30
    rag_poll_interval_seconds: int = 5
    rag_search_limit: int = 6
    rag_summary_chunks: int = 3

    # Teaching, quiz, and workflow
    # Teaching thresholds
    min_messages_before_day_complete: int = 8
    max_plan_days: int = 90
    quiz_chapter_interval: int = 1

    max_context_tokens: int = 8000
    max_response_tokens: int = 600
    default_temperature: float = 0.7

    # Workflow limits
    workflow_max_messages_before_continue_as_new: int = 500
    workflow_conversation_trim_threshold: int = 30
    workflow_conversation_keep_recent: int = 20
    workflow_conversation_context_window: int = 10
    workflow_inactivity_timeout_hours: int = 24

    # Quiz configuration
    quiz_question_type_weights: str = "0.5,0.25,0.25"
    quiz_passing_score: float = 0.7
    quiz_max_content_chars: int = 4000
    quiz_questions_per_quiz: int = 5
    attention_question_min_interval: int = 5
    attention_question_max_interval: int = 12
    attention_question_probability: float = 0.3
    
    # Cache TTLs (seconds)
    cache_ttl_user_state: int = 3600
    cache_ttl_chapter_chunks: int = 3600
    cache_ttl_chapter_summary: int = 86400
    cache_ttl_conversation: int = 1800
    cache_ttl_embeddings: int = 604800
    
    # Email (Resend)
    resend_api_key: Optional[str] = None
    verification_from_email: str = "Professor <noreply@professoros.com>"
    
    # Twilio/WhatsApp Configuration
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_whatsapp_number: str = "whatsapp:+14155238886"
    
    # Monitoring
    sentry_dsn: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
