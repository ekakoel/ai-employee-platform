#!/usr/bin/env sh
# Logical backup for AI Employee Platform (Postgres).
# Usage: ./scripts/backup_postgres.sh [output_dir]
set -e
OUT_DIR="${1:-./backups}"
mkdir -p "$OUT_DIR"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
FILE="$OUT_DIR/aiep_${STAMP}.sql.gz"

: "${DATABASE_URL:?Set DATABASE_URL (postgresql+psycopg://...)}"

# Strip SQLAlchemy driver prefix for pg_dump
PG_URL=$(echo "$DATABASE_URL" | sed 's#postgresql+psycopg://#postgresql://#')

echo "Backing up to $FILE"
pg_dump "$PG_URL" | gzip > "$FILE"
echo "Done: $FILE"
