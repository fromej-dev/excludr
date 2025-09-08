FROM ghcr.io/astral-sh/uv:python3.12-alpine

WORKDIR /code

COPY pyproject.toml .

RUN uv sync --no-cache-dir

COPY ./app /code/app

CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]