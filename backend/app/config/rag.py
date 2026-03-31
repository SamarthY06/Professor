"""RAG Service Configuration."""

from functools import lru_cache
from pydantic_settings import BaseSettings


class RAGConfig(BaseSettings):
    """Configuration for external RAG service integration."""
    
    # External RAG service URL (Textbook_RAG service)
    rag_base_url: str = "http://localhost:8001"
    rag_admin_username: str = ""
    rag_admin_password: str = ""
    rag_request_timeout: int = 30
    rag_poll_interval_seconds: int = 5
    rag_max_retries: int = 3
    rag_retry_delay_seconds: float = 1.0
    rag_max_connections: int = 10
    rag_keepalive_expiry: int = 30
    rag_token_refresh_buffer_seconds: int = 60
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"
    
    @property
    def auth_url(self) -> str:
        return f"{self.rag_base_url}/auth/login"
    
    @property
    def documents_url(self) -> str:
        return f"{self.rag_base_url}/documents"
    
    @property
    def search_url(self) -> str:
        return f"{self.rag_base_url}/search"
    
    def get_document_url(self, document_id: str) -> str:
        return f"{self.documents_url}/{document_id}"
    
    def get_document_progress_url(self, document_id: str) -> str:
        return f"{self.documents_url}/{document_id}/progress"
    
    def get_document_toc_url(self, document_id: str) -> str:
        return f"{self.documents_url}/{document_id}/toc"
    
    def get_document_chapters_url(self, document_id: str) -> str:
        return f"{self.documents_url}/{document_id}/chapters"


@lru_cache()
def get_rag_config() -> RAGConfig:
    return RAGConfig()


rag_config = get_rag_config()
