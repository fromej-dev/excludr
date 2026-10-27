FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /code

ENV UV_COMPILE_BYTECODE=1 \
    PATH="/code/.venv/bin:$PATH"

# Install dependencies first so this layer is cached until the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-cache

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

EXPOSE 8000

# Apply migrations, then serve.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
