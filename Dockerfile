FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY alembic ./alembic
COPY alembic.ini ./
COPY src ./src
COPY main.py ./

RUN pip install --no-cache-dir uv \
    && uv sync --frozen \
    && uv run playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

EXPOSE 8000

CMD ["sh", "-c", "uv run uvicorn facebook_api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]