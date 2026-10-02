from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


# ============================================================
# Base
# ============================================================

class Base(DeclarativeBase):
    """
    Base class untuk seluruh SQLAlchemy models.
    """
    pass


# ============================================================
# Database Engine
# ============================================================

DATABASE_URL = settings.database_url

connect_args: dict[str, object] = {}

if DATABASE_URL.startswith("sqlite"):
    # SQLite membutuhkan flag ini ketika digunakan oleh
    # FastAPI dengan beberapa thread.
    connect_args["check_same_thread"] = False


engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
)


# ============================================================
# Session Factory
# ============================================================

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


# ============================================================
# Database Initialization
# ============================================================

def init_db() -> None:
    """
    Initialize database schema.

    create_all():
        - Membuat tabel yang belum ada.
        - Tidak mengubah tabel yang sudah ada.

    migrate_sqlite_schema():
        - Menangani perubahan schema sederhana untuk SQLite
          pada database MVP yang sudah pernah dibuat.
    """

    # Pastikan semua model sudah di-import sebelum create_all()
    #
    # Import model di sini membantu memastikan SQLAlchemy
    # mengetahui seluruh table/model yang harus dibuat.
    #
    # Jangan hapus import ini walaupun terlihat tidak digunakan.
    from app.models import (  # noqa: F401
        agent_instance,
        # Tambahkan module model lain di sini jika project Anda
        # menggunakan import eksplisit.
    )

    Base.metadata.create_all(bind=engine)

    migrate_sqlite_schema()


# ============================================================
# Lightweight SQLite Migration
# ============================================================

def migrate_sqlite_schema() -> None:
    """
    Lightweight schema migration untuk MVP.

    SQLAlchemy create_all() hanya membuat table yang belum ada.
    Ia tidak menambahkan column baru ke table yang sudah ada.

    Fungsi ini menangani perubahan schema SQLite sederhana
    tanpa menghapus data existing.

    IMPORTANT:
    - Tidak digunakan untuk PostgreSQL.
    - Untuk production nanti sebaiknya diganti dengan Alembic.
    """

    # Migration ini hanya untuk SQLite.
    if not DATABASE_URL.startswith("sqlite"):
        return

    inspector = inspect(engine)

    table_names = inspector.get_table_names()

    # --------------------------------------------------------
    # agent_instances
    # --------------------------------------------------------

    if "agent_instances" not in table_names:
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("agent_instances")
    }

    # --------------------------------------------------------
    # subscription_id
    # --------------------------------------------------------

    if "subscription_id" not in columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    ALTER TABLE agent_instances
                    ADD COLUMN subscription_id VARCHAR(36)
                    """
                )
            )


# ============================================================
# FastAPI Database Dependency
# ============================================================

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency untuk mendapatkan database session.

    Contoh:

        @router.get("/example")
        def example(db: Session = Depends(get_db)):
            ...
    """

    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()