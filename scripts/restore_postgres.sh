#!/usr/bin/env sh
# Restore logical dump. WARNING: overwrites target database objects.
# Usage: ./scripts/restore_postgres.sh path/to/aiep_....sql.gz
set -e
DUMP="${1:?Usage: $0 path/to/dump.sql.gz}"
: "${DATABASE_URL:?Set DATABASE_URL}"

PG_URL=$(echo "$DATABASE_URL" | sed 's#postgresql+psycopg://#postgresql://#')

echo "Restoring $DUMP into $PG_URL"
gunzip -c "$DUMP" | psql "$PG_URL"
echo "Restore complete. Run: alembic upgrade head"
