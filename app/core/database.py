from typing import Annotated

from fastapi import Depends
from sqlmodel import create_engine, Session

from app.core.config import get_settings

settings = get_settings()


sqlite_url = settings.database_url

connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, connect_args=connect_args)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]

from app.features.users.models import *  # noqa: F403, E402
from app.features.projects.models import *  # noqa: F403, E402
