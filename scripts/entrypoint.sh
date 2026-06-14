#!/usr/bin/env bash
set -e

echo "[entrypoint] Waiting for database..."
until pg_isready -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" >/dev/null 2>&1; do
  sleep 1
done
echo "[entrypoint] Database is ready."

echo "[entrypoint] Running Alembic migrations..."
alembic upgrade head

echo "[entrypoint] Starting bot..."
exec python -m app.main
