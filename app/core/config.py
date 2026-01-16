from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Excludr"
    admin_email: str = "ej@fromejdevelopment.nl"
    database_url: str = "sqlite:///database.db"
    api_prefix: str = "/api/v1"
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    google_api_key: Optional[str] = None

    upload_directory: str = "/tmp/ris_uploads"
    pdf_storage_path: str = "/tmp/pdfs"

    model_config = SettingsConfigDict(env_file=".env")

    # Prefect settings
    prefect_api_url: str = "http://localhost:4200/api"

    # AI/LLM settings
    anthropic_api_key: Optional[str] = None
    default_llm_model: str = "claude-sonnet-4-20250514"
    screening_confidence_threshold: float = 0.7

    # Unpaywall settings for full-text retrieval
    unpaywall_email: Optional[str] = None

    # PubMed E-utilities settings
    pubmed_email: Optional[str] = None  # Required by NCBI for API usage
    pubmed_api_key: Optional[str] = None  # Optional, for higher rate limits

    # Database URL for PostgreSQL (used by Prefect workers)
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/appdb"


@lru_cache
def get_settings() -> Settings:
    return Settings()
