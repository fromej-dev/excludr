from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Excludr"
    database_url: str = "sqlite:///database.db"
    api_prefix: str = "/api/v1"
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Login rate limiting (in-memory sliding window per client IP + email)
    login_rate_limit_attempts: int = 10
    login_rate_limit_window_seconds: int = 300

    # CORS: browser origins allowed to call the API
    cors_origins: list[str] = ["http://localhost:5173"]

    # Maximum accepted size for uploaded files (RIS, PubMed, PDF), in megabytes
    max_upload_mb: int = 50
    google_api_key: Optional[str] = None

    upload_directory: str = "/tmp/ris_uploads"
    pdf_storage_path: str = "/tmp/pdfs"

    model_config = SettingsConfigDict(env_file=".env")

    # Prefect settings
    prefect_api_url: str = "http://localhost:4200/api"

    # AI/LLM settings
    anthropic_api_key: Optional[str] = None
    default_llm_model: str = "claude-sonnet-5-5"
    screening_confidence_threshold: float = 0.7
    # Max characters of full text sent to the screening model (longer text is truncated)
    screening_max_fulltext_chars: int = 150_000

    # Unpaywall settings for full-text retrieval
    unpaywall_email: Optional[str] = None

    # PubMed E-utilities settings
    pubmed_email: Optional[str] = None  # Required by NCBI for API usage
    pubmed_api_key: Optional[str] = None  # Optional, for higher rate limits


@lru_cache
def get_settings() -> Settings:
    return Settings()
