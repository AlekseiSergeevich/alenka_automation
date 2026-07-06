# Build from repository root: docker compose build
FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

COPY src/backend/requirements.txt /app/src/backend/requirements.txt
RUN apt-get update && \
    mkdir -p /usr/share/man/man1 && \
    apt-get install -y --no-install-recommends libreoffice && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --upgrade pip && \
    pip install -r src/backend/requirements.txt

COPY alembic.ini /app/alembic.ini
COPY src/backend /app/src/backend

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Overridden by docker-compose (host `db` service)
ENV DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/candy_forecast

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
