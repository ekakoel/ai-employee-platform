"""Job 29 — Integrations framework tests."""

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.services.seed import seed_catalog

engine = create_engine(
    "sqlite:///./test_integrations_job29.db",
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


def setup(client):
    co = client.post("/api/v1/companies", json={"name": "Integ Co"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={
            "name": "Owner",
            "email": "integ@test.local",
            "role": "owner",
            "password": "secret123",
        },
    ).json()
    return co["id"], {"X-User-ID": owner["id"]}


def _sign(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_create_and_list_integration(client):
    company_id, headers = setup(client)
    created = client.post(
        f"/api/v1/companies/{company_id}/integrations",
        headers=headers,
        json={
            "name": "Mailer",
            "type": "email_outbound",
            "config": {"from_address": "ops@example.com"},
            "event_map": {"message.received": "email.inbound"},
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["type"] == "email_outbound"
    assert "webhook_secret" in body
    assert "_webhook_secret" not in (body.get("config") or {})

    listed = client.get(
        f"/api/v1/companies/{company_id}/integrations",
        headers=headers,
    )
    assert listed.status_code == 200
    assert any(i["id"] == body["id"] for i in listed.json())


def test_webhook_bad_signature_rejected(client):
    company_id, headers = setup(client)
    created = client.post(
        f"/api/v1/companies/{company_id}/integrations",
        headers=headers,
        json={"name": "Hook", "type": "webhook_generic", "event_map": {}},
    ).json()
    iid = created["id"]
    body = json.dumps({"event": "ping", "n": 1}).encode()
    resp = client.post(
        f"/api/v1/companies/{company_id}/integrations/{iid}/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Signature": "sha256=deadbeef",
        },
    )
    assert resp.status_code == 401


def test_webhook_good_signature_accepted(client):
    company_id, headers = setup(client)
    created = client.post(
        f"/api/v1/companies/{company_id}/integrations",
        headers=headers,
        json={
            "name": "Hook OK",
            "type": "webhook_generic",
            "event_map": {"order.created": "commerce.order_created"},
        },
    ).json()
    secret = created["webhook_secret"]
    iid = created["id"]
    payload = {"event": "order.created", "order_id": "A1"}
    raw = json.dumps(payload).encode()
    resp = client.post(
        f"/api/v1/companies/{company_id}/integrations/{iid}/webhook",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Signature": _sign(secret, raw),
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["accepted"] is True
    assert data["automation_event"] == "commerce.order_created"


def test_email_stub_action(client):
    company_id, headers = setup(client)
    created = client.post(
        f"/api/v1/companies/{company_id}/integrations",
        headers=headers,
        json={
            "name": "Mail",
            "type": "email_outbound",
            "config": {"from_address": "noreply@co.local"},
        },
    ).json()
    resp = client.post(
        f"/api/v1/companies/{company_id}/integrations/{created['id']}/actions/email-send",
        headers=headers,
        json={"to": "user@x.com", "subject": "Hi", "body": "Hello"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued_stub"
    assert resp.json()["to"] == "user@x.com"


def test_unsupported_type(client):
    company_id, headers = setup(client)
    bad = client.post(
        f"/api/v1/companies/{company_id}/integrations",
        headers=headers,
        json={"name": "X", "type": "salesforce_full"},
    )
    assert bad.status_code == 400
