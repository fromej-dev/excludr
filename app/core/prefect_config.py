"""Prefect configuration and utilities for background task processing."""

from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

from sqlmodel import Session, create_engine

from app.core.config import get_settings


def get_prefect_engine():
    """Get a database engine for Prefect workers."""
    settings = get_settings()
    return create_engine(settings.database_url)


@contextmanager
def get_prefect_session():
    """Context manager for database sessions in Prefect tasks.

    Usage:
        with get_prefect_session() as session:
            # do database operations
            session.add(obj)
    """
    engine = get_prefect_engine()
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def run_flow_in_background(flow_fn: Callable[..., Any], *args: Any) -> None:
    """Await a Prefect flow from FastAPI ``BackgroundTasks``.

    A Prefect ``Flow`` object is not recognised as a coroutine function by
    Starlette, so ``background_tasks.add_task(some_async_flow, ...)`` would run
    it in a thread and silently drop the coroutine. Schedule this wrapper instead:
    ``background_tasks.add_task(run_flow_in_background, some_async_flow, ...)``.
    """
    await flow_fn(*args)
