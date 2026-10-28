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
- **Full-text retrieval**: owners trigger `POST /projects/{id}/articles/retrieve-fulltext` (bulk, Prefect flow `retrieve_fulltext_flow`) or `.../{aid}/retrieve-fulltext` (single). `app/features/research/fulltext_retrieval.py` tries Unpaywall (needs `UNPAYWALL_EMAIL`), PubMed Central OA PDF, then Europe PMC full-text XML (text only, no PDF). The source is stored in `Article.full_text_source` (`unpaywall|pmc|europepmc|manual`); failures stay in `awaiting_full_text` with `full_text_retrieval_error`. Tests must mock HTTP (`httpx.MockTransport`, see `tests/features/research/fulltext_helpers.py`), never the network.
- **Decision sources**: `ai_agent` | `human`
- **Criteria types**: `inclusion` | `exclusion` — each with a code, description, and rationale
- **Roles**: `owner` | `reviewer` | `viewer` per project (`ProjectMember`); enforced with `require_project_role(min_role)` from `app/features/projects/permissions.py` (viewer reads, reviewer also decides + runs AI, owner does everything else)
- **Dual screening & conflicts**: `Project.required_reviewers` (1 or 2). Each reviewer's latest human decision per article/stage counts; an article advances only when the required reviewers have decided and agree, otherwise it is *in conflict* (computed, no status value) and the owner resolves it (`is_resolution` decision). AI decisions never count as reviewers.
- **Billing (review passes)**: off unless `BILLING_ENABLED`. Projects without a `ProjectPlan` share a free allowance per owner account; a pass (`app/features/billing/plans.py`) is a one-off Stripe Checkout payment per project, valid 12 months. Usage = distinct articles with an AI decision per stage (re-screens are free). Limits are enforced in `run-ai`, `screen-ai` and the batch flow (402); an expired pass makes reviewer/owner writes return 402 via `require_project_role` (`allow_read_only=True` exempts e.g. delete and checkout). Stripe calls go through `billing/stripe_client.py` (httpx); tests mock it with `httpx.MockTransport`.
- **Account**: `/account` page. `PATCH /users/me` (name), `PUT /users/me/email` and `PUT /users/me/password` need the current password (throttled like login); an email change returns a new token pair because tokens name the email. `GET /billing/account` gives the free allowance and each owned project's pass and AI usage.
- **Reporting & audit**: PRISMA counts (from `ImportBatch` + decisions), CSV/RIS export, agreement stats (Cohen's kappa), and an append-only `AuditEvent` log

### Tech Stack

- **FastAPI** — web framework
- **SQLModel** — ORM (SQLAlchemy + Pydantic)
- **pydantic-ai** — AI screening agent
- **Alembic** — database migrations
- **Prefect** — workflow orchestration (file parsing, batch AI screening)
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

### Homepage Screenshots
```bash
# Seeds a fictional demo review on a fresh database and rewrites frontend/src/assets/screenshots/
cd frontend && npm run screenshots
```
Re-run after UI changes to the screening, conflicts or reports pages; never capture real project data.

### Database Migrations
```bash
# Create a new migration
alembic revision --autogenerate -m "description"

# Run migrations
alembic upgrade head
```

### Prefect
```bash
# Flows run in-process by default; start a Prefect server (UI on :4200) if wanted
prefect server start
```

### Docker Services
```bash
# Start PostgreSQL, Prefect server and the API (needs SECRET_KEY set)
docker-compose up -d
```

## Architecture

### Application Structure
- `app/main.py` - FastAPI app entry point
- `app/core/` - Core infrastructure (config, database, API router, Prefect config)
- `app/features/` - Feature modules (auth, users, projects, research, criteria, screening)

### Feature Module Pattern
Each feature in `app/features/` follows this structure:
- `models.py` - SQLModel database models
- `routers.py` - FastAPI route handlers
- `services.py` - Business logic
- `flows.py` - Prefect flows/tasks for background work (if applicable)
- `schemas.py` - Pydantic schemas for request/response (if applicable)

### Database
- SQLModel (SQLAlchemy + Pydantic) for ORM
- Models are imported in `app/core/database.py` for Alembic detection
- Use `SessionDep` type annotation for dependency injection in routes

### Background Tasks
- Prefect flows and tasks, defined in feature `flows.py` files
- `get_prefect_session()` (`app/core/prefect_config.py`) gives tasks a database session
- Flows that run inside the API process (e.g. batch AI screening) open their own `Session(engine)`; pass only primitive ids into flows

### Configuration
- Environment variables via `.env` file
- Settings defined in `app/core/config.py` using pydantic-settings
- Access settings via `get_settings()` (cached with `@lru_cache`)

### Testing
- pytest with fixtures in `tests/conftest.py`
- In-memory SQLite database with transaction rollback per test
- Prefect flows run synchronously in tests; tests monkeypatch `get_prefect_session` to reuse the test session
- Key fixtures: `client`, `session`, `auth_client`, `admin_client`, `a_user`, `a_project`, `auth_as`

### API Routes
- All routes prefixed with `/api/v1` (configurable via `api_prefix` setting)
- JWT authentication via Bearer token
