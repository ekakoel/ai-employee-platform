"""Job 45 — session bootstrap hydrate + relaxed hydrate permission."""

import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from tests.helpers import owner_setup, provision_company, bootstrap_demo, login_headers

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
    # auth-hardened: demo bootstrap instead of public company create
    _cid, _oid, _hdrs, _demo = provision_company(client)
    co = {"id": _cid}
    owner = {"id": _oid, "email": _demo.get("owner_email")}
    # Use reservation persona from bootstrap (invite-only; no POST /users)
    from tests.helpers import persona_headers
    try:
        _rid, res_headers = persona_headers(client, _demo, "reservation")
    except AssertionError:
        res_headers = _hdrs  # fallback owner if persona missing
    seed = client.post(
        f"/api/v1/companies/{co['id']}/demo/seed-reservation",
        headers=_hdrs,
        json={},
    )
    assert seed.status_code == 200, seed.text
    set_external_client(MockExternalSystemClient())
    hyd = client.post(
        f"/api/v1/companies/{co['id']}/inventory/hydrate",
        headers=res_headers,
        json={},
    )
    assert hyd.status_code == 200, hyd.text
    assert hyd.json()["hydrated"] >= 1
