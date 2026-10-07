"""initial schema baseline

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-07

Baseline revision for production. For greenfield Postgres:

  alembic upgrade head

For existing SQLite MVP databases, continue using create_all +
migrate_sqlite_schema until you cut over.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tables are managed via SQLAlchemy metadata for MVP.
    # Operators should run: Base.metadata.create_all or alembic with autogenerate
    # after pointing DATABASE_URL at Postgres.
    bind = op.get_bind()
    from app.core.database import Base
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    from app.core.database import Base
    import app.models  # noqa: F401

    Base.metadata.drop_all(bind=bind)
