# Backup & Restore (PostgreSQL)

**Job 24 — Production cutover**

## Prerequisites

- PostgreSQL 14+ (compose uses 16)
- `pg_dump` / `psql` client tools
- `DATABASE_URL=postgresql+psycopg://USER:PASS@HOST:5432/DB`

## Backup

```bash
export DATABASE_URL=postgresql+psycopg://aiep:aiep@localhost:5432/aiep
./scripts/backup_postgres.sh ./backups
```

Produces: `backups/aiep_YYYYMMDDTHHMMSSZ.sql.gz`

### Recommended cadence

| Environment | Cadence |
|-------------|---------|
| Production | Daily full + WAL if using continuous archiving |
| Staging | Weekly |
| Before migration | Always |

## Restore

```bash
export DATABASE_URL=postgresql+psycopg://aiep:aiep@localhost:5432/aiep
./scripts/restore_postgres.sh ./backups/aiep_....sql.gz
alembic upgrade head
```

## Docker Compose

```bash
docker compose exec db pg_dump -U aiep aiep | gzip > backup.sql.gz
gunzip -c backup.sql.gz | docker compose exec -T db psql -U aiep aiep
```

## Cutover checklist (SQLite → Postgres)

1. Start Postgres (`docker compose up -d db`).
2. Set `DATABASE_URL` to Postgres URL.
3. `alembic upgrade head`
4. (Optional) Export critical SQLite rows and import via scripts/app.
5. Point API/worker at Postgres; smoke-test `/health/ready`.
6. Keep SQLite file as cold backup for 7 days.

## Notes

- Application still supports SQLite for local/dev via `create_all` + `migrate_sqlite_schema`.
- Production containers run `alembic upgrade head` in the entrypoint before uvicorn.
