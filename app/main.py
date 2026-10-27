import logging
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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
    os.makedirs(settings.pdf_storage_path, exist_ok=True)
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


@app.get("/ping")
async def ping():
    return "pong"


def mount_frontend(app: FastAPI, dist_path: str) -> None:
    """Serve the built single-page app from ``dist_path``.

    Real files (``/assets/*``, ``/favicon.ico``) are served as-is; any other
    non-API path returns ``index.html`` so client-side routes survive a reload.
    Must be called after the API routers are included.
    """
    dist = os.path.realpath(dist_path)
    index = os.path.join(dist, "index.html")
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(dist, "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = os.path.realpath(os.path.join(dist, full_path))
        if (
            full_path
            and os.path.commonpath([dist, candidate]) == dist
            and os.path.isfile(candidate)
        ):
            return FileResponse(candidate)
        return FileResponse(index)


if settings.frontend_dist_path and os.path.isdir(settings.frontend_dist_path):
    mount_frontend(app, settings.frontend_dist_path)
else:

    @app.get("/")
    async def root():
        return {"message": "Excludr API"}
