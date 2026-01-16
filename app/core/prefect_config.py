"""Prefect configuration and utilities for background task processing."""

from contextlib import contextmanager

from sqlmodel import Session, create_engine

from app.core.config import get_settings


def get_prefect_engine():
    """Get a database engine for Prefect workers."""
    settings = get_settings()
    # Use DATABASE_URL for Prefect workers (PostgreSQL)
    # Fall back to database_url (SQLite) for development
    db_url = settings.DATABASE_URL or settings.database_url
    return create_engine(db_url)


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
