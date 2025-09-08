from contextlib import contextmanager

from celery import Celery
from sqlmodel import Session

from .config import get_settings
from .database import engine

settings = get_settings()

celery = Celery(
    __name__,
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.features.projects.tasks", "app.features.research.tasks"],
)

celery.autodiscover_tasks()

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


@contextmanager
def get_celery_session():
    """
    Provides a transactional scope around a series of operations for a Celery task.
    This is a standalone session manager since Celery workers are separate processes.
    """
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
