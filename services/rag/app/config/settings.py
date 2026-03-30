"""Application settings and configuration."""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "document-intelligence-rag"
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"

    # PostgreSQL
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = "raguser"
    postgres_password: str = "ragpassword"
    postgres_db: str = "ragdb"
    database_url: str = "postgresql+asyncpg://raguser:ragpassword@postgres:5432/ragdb"

    # Qdrant
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    qdrant_collection_name: str = "document_chunks"

    # Temporal
    temporal_host: str = "temporal"
    temporal_port: int = 7233
    temporal_namespace: str = "default"
    temporal_task_queue: str = "document-ingestion"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_vision_model: str = "gpt-4o"

    # Processing Configuration
    toc_pages_to_extract: int = 20
    chunk_size_min: int = 500
    chunk_size_max: int = 800
    chapter_batch_size: int = 5
    max_concurrent_chapters: int = 3

    # Storage
    upload_dir: Path = Path("/app/uploads")
    processed_dir: Path = Path("/app/processed")

    @property
    def temporal_address(self) -> str:
        """Get Temporal server address."""
        return f"{self.temporal_host}:{self.temporal_port}"

    @property
    def sync_database_url(self) -> str:
        """Get synchronous database URL for migrations."""
        return self.database_url.replace("postgresql+asyncpg", "postgresql+psycopg2")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
