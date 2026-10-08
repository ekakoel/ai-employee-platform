"""schema sync Job 15–23 tables and columns

Revision ID: 0002_schema_sync
Revises: 0001_initial
Create Date: 2026-10-08

Idempotent sync for production Postgres cutover after MVP growth.
Uses SQLAlchemy metadata create_all (safe if tables exist) and
explicit column adds for common drift cases.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision: str = "0002_schema_sync"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(table: str, column: str, ddl: str) -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns(table)}
    if column in cols:
        return
    bind.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))


def upgrade() -> None:
    bind = op.get_bind()
    from app.core.database import Base
    import app.models  # noqa: F401

    # Create any tables added after baseline (notifications, plans, etc.)
    Base.metadata.create_all(bind=bind)

    # Column drift that create_all does not fix on existing tables
    _add_column_if_missing("users", "password_hash", "password_hash VARCHAR(255)")
    _add_column_if_missing("users", "department_id", "department_id VARCHAR(36)")
    _add_column_if_missing(
        "users", "is_platform_admin", "is_platform_admin BOOLEAN DEFAULT FALSE"
    )
    _add_column_if_missing(
        "companies", "is_active", "is_active BOOLEAN DEFAULT TRUE"
    )
    _add_column_if_missing(
        "agent_instances", "department_id", "department_id VARCHAR(36)"
    )
    _add_column_if_missing(
        "agent_instances", "supervisor_user_id", "supervisor_user_id VARCHAR(36)"
    )


def downgrade() -> None:
    # Non-destructive downgrade: leave columns/tables in place.
    pass
