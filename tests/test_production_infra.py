"""Job 13 — Production infrastructure smoke tests."""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.core.security import create_access_token, decode_access_token
from app.main import app
from app.services.seed import seed_catalog
from app.storage.base import LocalObjectStorage


engine = create_engine(
    "sqlite:///./test_production_infra.db",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_catalog(db)

    def override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    prev = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    if prev is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = prev


def test_health_and_ready():
    c = TestClient(app)
    h = c.get("/health")
    assert h.status_code == 200
    assert h.json()["status"] == "ok"
    assert "env" in h.json()

    r = c.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "not_ready")
    assert "database" in body
    assert "storage_backend" in body


def test_request_id_header():
    c = TestClient(app)
    res = c.get("/health", headers={"X-Request-ID": "test-req-123"})
    assert res.headers.get("X-Request-ID") == "test-req-123"


def test_jwt_roundtrip():
    token = create_access_token(subject="user-1", company_id="co-1")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-1"
    assert payload["company_id"] == "co-1"


def test_issue_token_endpoint(client):
    co = client.post("/api/v1/companies", json={"name": "Auth Co"}).json()
    user = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={"name": "Owner", "email": "owner@auth.test", "role": "owner"},
    ).json()
    tok = client.post(
        "/api/v1/auth/token",
        json={"company_id": co["id"], "email": "owner@auth.test"},
    )
    assert tok.status_code == 200, tok.text
    body = tok.json()
    assert body["token_type"] == "bearer"
    assert body["user_id"] == user["id"]
    assert body["access_token"]

    bad = client.post(
        "/api/v1/auth/token",
        json={"company_id": co["id"], "email": "nobody@auth.test"},
    )
    assert bad.status_code == 401


def test_local_object_storage():
    with tempfile.TemporaryDirectory() as tmp:
        store = LocalObjectStorage(tmp)
        key = "docs/company-a/file.txt"
        store.put_bytes(key, b"hello production", content_type="text/plain")
        assert store.exists(key)
        assert store.get_bytes(key) == b"hello production"
        store.delete(key)
        assert not store.exists(key)


def test_storage_path_traversal_blocked():
    with tempfile.TemporaryDirectory() as tmp:
        store = LocalObjectStorage(tmp)
        with pytest.raises(ValueError):
            store.put_bytes("../outside.txt", b"nope")


def test_alembic_env_imports():
    from alembic import config as alembic_config

    cfg = alembic_config.Config("alembic.ini")
    assert cfg.get_main_option("script_location") == "alembic"


def test_dockerfile_and_compose_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "Dockerfile").is_file()
    assert (root / "docker-compose.yml").is_file()
    assert (root / "alembic" / "versions" / "0001_initial_schema.py").is_file()
