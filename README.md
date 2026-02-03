# Excludr

Excludr is a systematic review screening tool that helps researchers evaluate full-text articles against inclusion and exclusion criteria. It uses an AI agent (powered by pydantic-ai) to assist with screening decisions, reducing the manual burden of systematic reviews.

## What It Does

In a systematic review, researchers must screen hundreds or thousands of articles to determine which ones meet their study criteria. This is time-consuming and error-prone. Excludr streamlines this process by:

- Letting researchers define structured **inclusion/exclusion criteria** with codes, descriptions, and rationale
- Importing articles from **RIS** and **PubMed** formats
- Using an **AI screening agent** to evaluate full-text articles against each criterion, producing confidence scores and reasoning
- Supporting **human review** alongside AI decisions, with the ability to override
- Tracking each article through a screening pipeline from import to final decision

The primary focus is on **full-text review** — the stage where researchers assess complete articles rather than just titles and abstracts.

## Screening Pipeline

```
imported → screening → awaiting_full_text → full_text_retrieved → included / excluded
```

Each screening decision records:
- The decision (include / exclude / uncertain)
- The source (AI agent or human reviewer)
- Per-criterion evaluations
- Confidence score and reasoning

## Tech Stack

| Component | Technology |
|---|---|
| Backend | FastAPI |
| ORM | SQLModel (SQLAlchemy + Pydantic) |
| AI Agent | pydantic-ai |
| Background Tasks | Celery + Redis |
| Migrations | Alembic |
| Workflows | Prefect |
| Frontend | Vue 3 (in progress) |
| Database | PostgreSQL |

## Getting Started

### Prerequisites

- Python 3.11+
- Docker and Docker Compose (for PostgreSQL, Redis, Flower)

### Setup

```bash
# Start database and services
docker-compose up -d

# Install dependencies
pip install -e ".[dev]"

# Run migrations
alembic upgrade head

# Start the dev server
uvicorn app.main:app --reload
```

### Running Tests

```bash
pytest
```

### Linting

```bash
ruff check --fix .
ruff format .
```

## Project Structure

```
app/
  core/           # Config, database, API router, Celery
  features/
    auth/         # JWT authentication
    users/        # User management
    projects/     # Review projects, article import (RIS/PubMed)
    research/     # Articles, AI screening agent
    criteria/     # Inclusion/exclusion criteria
    screening/    # Screening decisions (AI + human)
```

Each feature module follows a consistent pattern: `models.py`, `routers.py`, `services.py`, and optionally `schemas.py` and `tasks.py`.
