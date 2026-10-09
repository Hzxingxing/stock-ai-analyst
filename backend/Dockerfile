FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.17 /uv /uvx /bin/

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/backend \
    TZ=Asia/Shanghai

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

COPY backend/app ./backend/app
COPY backend/alembic.ini ./backend/alembic.ini
COPY backend/src/migrations ./backend/src/migrations

EXPOSE 8000
CMD ["uv", "run", "--project", "/app", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
