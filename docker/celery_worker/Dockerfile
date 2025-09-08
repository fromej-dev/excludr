FROM ghcr.io/astral-sh/uv:python3.12-alpine

WORKDIR /code

COPY pyproject.toml .

RUN uv sync --no-cache-dir

COPY ./app /code/app

CMD [".venv/bin/celery", "-A", "app.core.celery.celery", "worker", "--loglevel=info"]