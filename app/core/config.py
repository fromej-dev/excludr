from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Awesome API"
    admin_email: str = "ej@fromejdevelopment.nl"
    database_url: str = "sqlite:///database.db"
    api_prefix: str = "/api/v1"
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    google_api_key: Optional[str] = None

    upload_directory: str = "/tmp/ris_uploads"

    model_config = SettingsConfigDict(env_file=".env")

    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/appdb"


@lru_cache
def get_settings() -> Settings:
    return Settings()
