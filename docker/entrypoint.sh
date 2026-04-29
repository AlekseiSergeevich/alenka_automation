#!/bin/sh
set -e
cd /app
python -m alembic upgrade head
if [ "${UVICORN_RELOAD:-}" = "1" ] || [ "${UVICORN_RELOAD:-}" = "true" ]; then
  exec python -m uvicorn src.backend.app.main:app --host 0.0.0.0 --port 8000 \
    --reload --reload-dir /app/src/backend
else
  exec python -m uvicorn src.backend.app.main:app --host 0.0.0.0 --port 8000
fi
