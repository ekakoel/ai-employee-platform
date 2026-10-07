from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


DATABASE_URL = settings.database_url

connect_args: dict = {}
engine_kwargs: dict = {
    "pool_pre_ping": True,
}

if settings.is_sqlite:
    connect_args["check_same_thread"] = False
else:
    engine_kwargs["pool_size"] = settings.db_pool_size
    engine_kwargs["max_overflow"] = settings.db_max_overflow

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    **engine_kwargs,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def init_db() -> None:
    """Create tables and run lightweight SQLite column migrations."""
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    migrate_sqlite_schema()


def migrate_sqlite_schema() -> None:
    """Lightweight SQLite column adds for MVP; production should use Alembic."""
    if not settings.is_sqlite:
        return

    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    if "agent_instances" not in table_names:
        return

    columns = {c["name"] for c in inspector.get_columns("agent_instances")}
    if "subscription_id" not in columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE agent_instances "
                    "ADD COLUMN subscription_id VARCHAR(36)"
                )
            )

    if "users" in table_names:
        user_cols = {c["name"] for c in inspector.get_columns("users")}
        if "password_hash" not in user_cols:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE users "
                        "ADD COLUMN password_hash VARCHAR(255)"
                    )
                )


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
