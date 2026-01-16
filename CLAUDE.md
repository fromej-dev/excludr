# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Excludr is a FastAPI application for research project management. It uses SQLModel for database models, Celery for background tasks, and Alembic for migrations.

## Common Commands

### Development Server
```bash
uvicorn app.main:app --reload
```

### Tests
```bash
# Run all tests with coverage
pytest

# Run a single test file
pytest tests/features/projects/test_upload.py

# Run a specific test
pytest tests/features/projects/test_upload.py::test_function_name -v
```

### Linting and Formatting
```bash
# Lint and auto-fix
ruff check --fix .

# Format code
ruff format .
```

### Database Migrations
```bash
# Create a new migration
alembic revision --autogenerate -m "description"

# Run migrations
alembic upgrade head
```

### Celery Worker
```bash
celery -A app.core.celery.celery worker --loglevel=info
```

### Docker Services
```bash
# Start PostgreSQL, Redis, and Flower (Celery monitoring)
docker-compose up -d
```

## Architecture

### Application Structure
- `app/main.py` - FastAPI app entry point
- `app/core/` - Core infrastructure (config, database, API router, Celery)
- `app/features/` - Feature modules (auth, users, projects, research)

### Feature Module Pattern
Each feature in `app/features/` follows this structure:
- `models.py` - SQLModel database models
- `routers.py` - FastAPI route handlers
- `services.py` - Business logic
- `tasks.py` - Celery background tasks (if applicable)
- `schemas.py` - Pydantic schemas for request/response (if applicable)

### Database
- SQLModel (SQLAlchemy + Pydantic) for ORM
- Models are imported in `app/core/database.py` for Alembic detection
- Use `SessionDep` type annotation for dependency injection in routes

### Background Tasks
- Celery with Redis broker
- Tasks defined in feature `tasks.py` files
- `get_celery_session()` context manager for database access in workers
- Task modules registered in `app/core/celery.py`

### Configuration
- Environment variables via `.env` file
- Settings defined in `app/core/config.py` using pydantic-settings
- Access settings via `get_settings()` (cached with `@lru_cache`)

### Testing
- pytest with fixtures in `tests/conftest.py`
- In-memory SQLite database with transaction rollback per test
- Celery runs in eager mode during tests (synchronous execution)
- Key fixtures: `client`, `session`, `auth_client`, `admin_client`, `a_user`, `a_project`, `auth_as`

### API Routes
- All routes prefixed with `/api/v1` (configurable via `api_prefix` setting)
- JWT authentication via Bearer token
