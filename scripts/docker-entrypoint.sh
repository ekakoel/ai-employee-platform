#!/usr/bin/env sh
set -e

echo "[entrypoint] Waiting for database migrations..."

# Run Alembic to head (Postgres production path)
if command -v alembic >/dev/null 2>&1; then
  alembic upgrade head
  echo "[entrypoint] alembic upgrade head — OK"
else
  echo "[entrypoint] alembic not found; skipping migrations" >&2
fi

# Optional seed of catalog/plans is handled at API startup / first request

exec "$@"
