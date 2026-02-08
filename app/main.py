import os

from fastapi import FastAPI

from app.core.api import router
from app.core.config import get_settings

settings = get_settings()


def lifespan(app: FastAPI):
    print("Starting the application")
    # Auto-create tables for SQLite (used in E2E/development).
    # Production uses Alembic migrations with PostgreSQL.
    if settings.database_url.startswith("sqlite"):
        from sqlmodel import SQLModel
        from app.core.database import engine

        SQLModel.metadata.create_all(engine)
    os.makedirs(settings.upload_directory, exist_ok=True)
    yield
    print("Stopping the application")


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.include_router(router)


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/ping")
async def ping():
    return "pong"
