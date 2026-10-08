"""Job 25 — S3 object storage (mocked client) + knowledge path."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.services.seed import seed_catalog
from app.storage.base import LocalObjectStorage, get_storage
from app.storage.s3 import S3ObjectStorage


class FakeBody:
    def __init__(self, data: bytes):
        self._data = data

    def read(self):
        return self._data


def test_s3_put_get_exists_delete_with_mock_client():
    store: dict[str, bytes] = {}
    client = MagicMock()

    def put_object(**kwargs):
        store[kwargs["Key"]] = kwargs["Body"]
        return {}

    def get_object(**kwargs):
        key = kwargs["Key"]
        if key not in store:
            err = Exception("NoSuchKey")
            err.response = {"Error": {"Code": "NoSuchKey"}}  # type: ignore[attr-defined]
            raise err
        return {"Body": FakeBody(store[key])}

    def head_object(**kwargs):
        if kwargs["Key"] not in store:
            raise Exception("404")
        return {}

    def delete_object(**kwargs):
        store.pop(kwargs["Key"], None)
        return {}

    client.put_object.side_effect = put_object
    client.get_object.side_effect = get_object
    client.head_object.side_effect = head_object
    client.delete_object.side_effect = delete_object

    s3 = S3ObjectStorage(bucket="test-bucket", client=client)
    key = s3.put_bytes("documents/c1/file.txt", b"hello", content_type="text/plain")
    assert key == "documents/c1/file.txt"
    assert s3.exists(key)
    assert s3.get_bytes(key) == b"hello"
    s3.delete(key)
    assert not s3.exists(key)


def test_s3_requires_bucket():
    with pytest.raises(ValueError, match="S3_BUCKET"):
        S3ObjectStorage(bucket="", client=MagicMock())


def test_get_storage_s3_backend(monkeypatch):
    from app.core import config as cfg_mod

    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "my-bucket")
    cfg_mod.settings = cfg_mod.Settings()
    # inject client by constructing S3ObjectStorage with mock via monkeypatch on boto3
    mock_client = MagicMock()
    monkeypatch.setattr(
        "app.storage.s3.S3ObjectStorage._build_client",
        lambda self: mock_client,
    )
    storage = get_storage()
    assert isinstance(storage, S3ObjectStorage)
    assert storage.bucket == "my-bucket"
    # reset
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    cfg_mod.settings = cfg_mod.Settings()


def test_get_storage_local_default(tmp_path, monkeypatch):
    from app.core import config as cfg_mod

    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(tmp_path))
    cfg_mod.settings = cfg_mod.Settings()
    storage = get_storage()
    assert isinstance(storage, LocalObjectStorage)
    storage.put_bytes("a/b.txt", b"x")
    assert storage.get_bytes("a/b.txt") == b"x"


engine = create_engine(
    "sqlite:///./test_s3_storage_job25.db",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app.core import config as cfg_mod

    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(tmp_path / "obj"))
    cfg_mod.settings = cfg_mod.Settings()

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
    cfg_mod.settings = cfg_mod.Settings()


def test_document_upload_uses_storage(client, tmp_path, monkeypatch):
    from app.core import config as cfg_mod

    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(tmp_path / "docs_store"))
    cfg_mod.settings = cfg_mod.Settings()

    co = client.post("/api/v1/companies", json={"name": "Storage Co"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={
            "name": "Owner",
            "email": "storage@test.local",
            "role": "owner",
            "password": "secret123",
        },
    ).json()
    headers = {"X-User-ID": owner["id"]}

    # Find document upload endpoint
    files = {"file": ("note.txt", b"hello knowledge storage", "text/plain")}
    # try common paths
    path = f"/api/v1/companies/{co['id']}/knowledge/documents"
    resp = client.post(path, headers=headers, files=files)
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    assert body.get("status") in ("ready", "READY", "processing", "failed") or "id" in body
    store_root = Path(tmp_path / "docs_store")
    found = list(store_root.rglob("*"))
    found = [f for f in found if f.is_file()]
    assert found, f"expected stored file under {store_root}, body={body}"
