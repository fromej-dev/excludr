import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.api import router
from app.core.config import Settings, get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

MIN_SECRET_KEY_LENGTH = 32


def warn_if_weak_secret(config: Settings) -> None:
    """Log a warning when the JWT signing key is shorter than recommended."""
    if len(config.secret_key) < MIN_SECRET_KEY_LENGTH:
        logger.warning(
            "SECRET_KEY is shorter than %d characters; use a long random value "
            "in production.",
            MIN_SECRET_KEY_LENGTH,
        )


def lifespan(app: FastAPI):
    logger.info("Starting the application")
    warn_if_weak_secret(settings)
    # Auto-create tables for SQLite (used in E2E/development).
    # Production uses Alembic migrations with PostgreSQL.
    if settings.database_url.startswith("sqlite"):
        from sqlmodel import SQLModel
        from app.core.database import engine

        SQLModel.metadata.create_all(engine)
    os.makedirs(settings.upload_directory, exist_ok=True)
    yield
    logger.info("Stopping the application")


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/ping")
async def ping():
    return "pong"
