from fastapi import FastAPI

from app.core.api import router
from app.core.config import get_settings


def lifespan(app: FastAPI):
    print("Starting the application")
    # not needed since we are using Alembic
    # create_db_and_tables()
    yield
    print("Stopping the application")


settings = get_settings()

app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.include_router(router)


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/ping")
async def ping():
    return "pong"
