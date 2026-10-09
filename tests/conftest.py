"""Keep disposable SQLite fixtures fast without changing application databases."""

from pathlib import Path
import sqlite3

from sqlalchemy import event
from sqlalchemy.engine import Engine


@event.listens_for(Engine, "connect")
def disposable_sqlite_settings(connection, _record):
    if not isinstance(connection, sqlite3.Connection):
        return
    cursor = connection.cursor()
    try:
        databases = cursor.execute("PRAGMA database_list").fetchall()
        for _, name, filename in databases:
            if name == "main" and Path(filename).name.startswith("test_"):
                # These files are recreated by fixtures; crash durability is not
                # under test. Leave locking, isolation, and production settings alone.
                cursor.execute("PRAGMA synchronous=OFF")
                break
    finally:
        cursor.close()
