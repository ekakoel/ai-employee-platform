"""Job 24 — Alembic migration path tests."""

from pathlib import Path
import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


ROOT = Path(__file__).resolve().parents[1]


def _alembic_cfg(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_alembic_upgrade_head_sqlite(tmp_path, monkeypatch):
    db_path = tmp_path / "alembic_job24.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    # settings may already be imported — force via alembic env reading os.environ
    # Reload is heavy; alembic env.py calls settings.database_url each run
    # pydantic settings may cache — clear if needed
    from app.core import config as cfg_mod
    cfg_mod.settings = cfg_mod.Settings()

    cfg = _alembic_cfg(url)
    command.upgrade(cfg, "head")

    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names())
    for required in (
        "companies",
        "users",
        "agent_instances",
        "tasks",
        "notifications",
        "plans",
        "conversations",
        "alembic_version",
    ):
        assert required in tables, f"missing table {required} in {tables}"

    with engine.connect() as conn:
        ver = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert ver == "0002_schema_sync"


def test_docker_entrypoint_script_exists():
    script = ROOT / "scripts" / "docker-entrypoint.sh"
    assert script.is_file()
    text_body = script.read_text()
    assert "alembic upgrade head" in text_body


def test_backup_docs_exist():
    assert (ROOT / "docs" / "BACKUP_RESTORE.md").is_file()
    assert (ROOT / "scripts" / "backup_postgres.sh").is_file()
    assert (ROOT / "scripts" / "restore_postgres.sh").is_file()


def test_dockerfile_uses_entrypoint():
    docker = (ROOT / "Dockerfile").read_text()
    assert "docker-entrypoint.sh" in docker
    assert "ENTRYPOINT" in docker
