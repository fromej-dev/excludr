# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Git Workflow

**Always follow this workflow for any task:**

1. **Create a feature branch** before starting work:
   ```bash
   git checkout -b feature/<short-description>
   # Examples: feature/screening-agent, feature/criteria-crud, fix/auth-bug
   ```

2. **Commit frequently** with clear messages describing changes

3. **Create a pull request** when the task is complete:
   ```bash
   git push -u origin <branch-name>
   gh pr create --title "Description" --body "Summary of changes"
   ```

4. **Never commit directly to master/main** - always use feature branches

## Project Overview

Excludr is a **systematic review screening tool** for researchers. In a systematic review, researchers must screen large numbers of articles against predefined inclusion and exclusion criteria. Excludr focuses on the **full-text review stage**, using a **pydantic-ai agent** to assist with screening decisions.

### Core Workflow

1. A researcher creates a **project** with a review question
2. They import articles (RIS or PubMed format)
3. They define **inclusion/exclusion criteria** (e.g., I1, E1) with descriptions and rationale
4. Articles are screened against criteria — either by the **AI screening agent** or by **human reviewers**
5. The AI agent evaluates each article's full text, produces per-criterion assessments with confidence scores and reasoning, and recommends include/exclude/uncertain
6. Human reviewers can review AI decisions, override them, or screen independently
7. Articles reach a final decision: **included** or **excluded**

### Key Concepts

- **Article pipeline**: `imported → screening → awaiting_full_text → full_text_retrieved → included/excluded`
- **Screening stages**: `title_abstract` | `full_text` | `completed`
- **Decision sources**: `ai_agent` | `human`
- **Criteria types**: `inclusion` | `exclusion` — each with a code, description, and rationale

### Tech Stack

- **FastAPI** — web framework
- **SQLModel** — ORM (SQLAlchemy + Pydantic)
- **pydantic-ai** — AI screening agent
- **Celery + Redis** — background tasks
- **Alembic** — database migrations
- **Prefect** — workflow orchestration for file parsing
- **Vue 3** — frontend (in progress)

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
- `app/features/` - Feature modules (auth, users, projects, research, criteria, screening)

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
