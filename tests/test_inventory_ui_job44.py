"""Job 44 — inventory workspace UI markers and API list."""

import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from tests.helpers import owner_setup, provision_company, bootstrap_demo, login_headers

from app.main import app

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]


def test_inventory_nav_and_view():
    html = client.get("/workspace").text
    assert 'data-view="inventory"' in html
    assert 'id="view-inventory"' in html
    assert "btnInvSeed" in html
    assert "btnInvHydrate" in html


def test_inventory_js_loader():
    js = (ROOT / "app/static/workspace/app.js").read_text(encoding="utf-8")
    assert "async function loadInventory" in js
    assert "/inventory/hydrate" in js


def test_inventory_api_after_seed():
    suffix = uuid.uuid4().hex[:8]
    # auth-hardened: demo bootstrap instead of public company create
    _cid, _oid, _hdrs, _demo = provision_company(client)
    co = {"id": _cid}
    owner = {"id": _oid, "email": _demo.get("owner_email")}
    seed = client.post(
        f"/api/v1/companies/{co['id']}/demo/seed-reservation",
        headers=_hdrs,
        json={},
    )
    assert seed.status_code == 200, seed.text
    listed = client.get(
        f"/api/v1/companies/{co['id']}/inventory",
        headers=_hdrs,
    )
    assert listed.status_code == 200, listed.text
    assert len(listed.json()["items"]) >= 3
