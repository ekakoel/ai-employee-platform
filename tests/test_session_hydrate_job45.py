"""Job 45 — session bootstrap hydrate + relaxed hydrate permission."""

import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.tools.connectors import MockExternalSystemClient, set_external_client

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]


def test_app_js_bootstrap_session_environment():
    js = (ROOT / "app/static/workspace/app.js").read_text(encoding="utf-8")
    assert "async function bootstrapSessionEnvironment" in js
    assert js.count("bootstrapSessionEnvironment()") >= 3
    assert "/inventory/hydrate" in js


def test_reservation_can_hydrate():
    set_external_client(MockExternalSystemClient())
    suffix = uuid.uuid4().hex[:8]
    co = client.post("/api/v1/companies", json={"name": f"Hyd45 {suffix}"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={
            "name": "Owner",
            "email": f"owner-{suffix}@h45.test",
            "role": "owner",
            "password": "demo12345",
        },
    ).json()
    res_user = client.post(
        f"/api/v1/companies/{co['id']}/users",
        headers={"X-User-ID": owner["id"]},
        json={
            "name": "Res",
            "email": f"res-{suffix}@h45.test",
            "role": "reservation",
            "password": "demo12345",
        },
    ).json()
    seed = client.post(
        f"/api/v1/companies/{co['id']}/demo/seed-reservation",
        headers={"X-User-ID": owner["id"]},
        json={},
    )
    assert seed.status_code == 200, seed.text
    set_external_client(MockExternalSystemClient())
    hyd = client.post(
        f"/api/v1/companies/{co['id']}/inventory/hydrate",
        headers={"X-User-ID": res_user["id"]},
        json={},
    )
    assert hyd.status_code == 200, hyd.text
    assert hyd.json()["hydrated"] >= 1
