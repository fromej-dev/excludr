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
| Migrations | Alembic |
| Background work / workflows | Prefect |
| Frontend | Vue 3 (in progress) |
| Database | PostgreSQL |

## Getting Started

### Prerequisites

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Docker and Docker Compose (for PostgreSQL and the Prefect server)

### Setup

```bash
# Start database and services (add --build to also run the API container;
# it needs SECRET_KEY set in your environment)
docker-compose up -d postgres prefect-server

# Install dependencies
uv sync

# Run migrations
uv run alembic upgrade head

# Start the dev server
uv run uvicorn app.main:app --reload
```

### Running Tests

```bash
uv run pytest
```

### Linting

```bash
ruff check --fix .
ruff format .
```

## Billing (review passes)

Billing is off by default, so development and self-hosted installs have no limits.
To sell review passes, turn it on with these environment variables:

| Variable | Purpose |
|---|---|
| `BILLING_ENABLED=true` | Enforce the free allowance, passes and read-only expiry |
| `STRIPE_SECRET_KEY` | Stripe API key (`sk_test_...` until going live) |
| `STRIPE_WEBHOOK_SECRET` | Signing secret of the webhook endpoint (`whsec_...`) |
| `PUBLIC_APP_URL` | Public URL of the app; Stripe returns the browser here after payment |
| `STRIPE_AUTOMATIC_TAX=true` | Optional; needs Stripe Tax set up in the Stripe dashboard first |
| `VITE_CONTACT_EMAIL` | Optional, at frontend build time; shows contact links on the home page |

In Stripe, add a webhook endpoint at `<PUBLIC_APP_URL>/api/v1/billing/webhook` for the
events `checkout.session.completed` and `checkout.session.async_payment_succeeded`.
No products need to be created in Stripe: prices come from
`app/features/billing/plans.py`, which also feeds the home page.

For local testing, the Stripe CLI can forward events:
`stripe listen --forward-to localhost:8000/api/v1/billing/webhook`.

Superusers can grant a pass without Stripe (invoice or PO payments, pilots):
`POST /api/v1/billing/admin/projects/{id}/grant` with `{"tier": "pass_250"}`, or
`{"tier": "custom", "fulltext_limit": 3000, "days": 365}`.

## Project Structure

```
app/
  core/           # Config, database, API router, Prefect config
  features/
    auth/         # JWT authentication
    users/        # User management
    projects/     # Review projects, article import (RIS/PubMed)
    research/     # Articles, AI screening agent
    criteria/     # Inclusion/exclusion criteria
    screening/    # Screening decisions (AI + human)
```

Each feature module follows a consistent pattern: `models.py`, `routers.py`, `services.py`, and optionally `schemas.py` and `flows.py` (Prefect).
