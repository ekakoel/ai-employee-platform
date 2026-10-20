"""Job 39 — durable company inventory survives empty connector."""

import uuid

from fastapi.testclient import TestClient

from tests.helpers import owner_setup, provision_company, bootstrap_demo, login_headers

from app.main import app
from app.tools.base import ToolContext
from app.tools.connectors import MockExternalSystemClient, set_external_client
from app.tools.domain import availability_records
from app.core.database import SessionLocal

client = TestClient(app)


def test_inventory_persists_and_matches_without_connector_rows():
    set_external_client(MockExternalSystemClient())  # empty connector
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

    # Wipe process connector — DB must still serve availability when db is passed
    set_external_client(MockExternalSystemClient())
    db = SessionLocal()
    try:
        ctx = ToolContext(
            company_id=co["id"],
            agent_instance_id="a1",
            task_id=None,
            db=db,
        )
        rows = availability_records(
            ctx,
            {
                "check_in": "2026-10-30",
                "check_out": "2026-10-31",
                "guests": 2,
                "location": "Alila",
            },
        )
        assert len(rows) >= 1
    finally:
        db.close()


def test_hydrate_endpoint():
    set_external_client(MockExternalSystemClient())
    suffix = uuid.uuid4().hex[:8]
    # auth-hardened: demo bootstrap instead of public company create
    _cid, _oid, _hdrs, _demo = provision_company(client)
    co = {"id": _cid}
    owner = {"id": _oid, "email": _demo.get("owner_email")}
    client.post(
        f"/api/v1/companies/{co['id']}/demo/seed-reservation",
        headers=_hdrs,
        json={},
    )
    set_external_client(MockExternalSystemClient())
    res = client.post(
        f"/api/v1/companies/{co['id']}/inventory/hydrate",
        headers=_hdrs,
        json={},
    )
    assert res.status_code == 200, res.text
    assert res.json()["hydrated"] >= 3
