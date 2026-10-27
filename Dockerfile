# Production image: builds the Vue frontend and serves it from the FastAPI app.

# ---- Frontend build ----
FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- API ----
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /code

ENV UV_COMPILE_BYTECODE=1 \
    PATH="/code/.venv/bin:$PATH" \
    FRONTEND_DIST_PATH=/code/frontend_dist \
    PDF_STORAGE_PATH=/data/pdfs

# Install dependencies first so this layer is cached until the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-cache

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY --from=frontend /frontend/dist ./frontend_dist

EXPOSE 8000

# Apply migrations, then serve. PORT is provided by the platform (e.g. Railway).
# --proxy-headers so client IPs (used by the login rate limiter) come from X-Forwarded-For.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
