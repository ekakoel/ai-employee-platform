"""Job 37 — grant operational agent access for non-admin roles."""

import uuid

from fastapi.testclient import TestClient

from tests.helpers import owner_setup, provision_company, bootstrap_demo, login_headers

from app.main import app

client = TestClient(app)


def _setup():
    suffix = uuid.uuid4().hex[:8]
    # auth-hardened: demo bootstrap instead of public company create
    _cid, _oid, _hdrs, _demo = provision_company(client)
    co = {"id": _cid}
    owner = {"id": _oid, "email": _demo.get("owner_email")}
    member = {"id": None}  # invite-only API; use bootstrap personas
    catalog = client.get("/api/v1/agent-catalog").json()
    hire = client.post(
        f"/api/v1/companies/{co['id']}/agents/{catalog[0]['id']}/hire",
        headers=_hdrs,
        json={"name": f"Agent {suffix}"},
    )
    assert hire.status_code in (200, 201), hire.text
    agent_id = hire.json()["id"]
    return co["id"], owner["id"], res["id"], agent_id


def test_reservation_blocked_until_grant():
    company_id, owner_id, res_id, agent_id = _setup()
    # create task should fail without access
    denied = client.post(
        f"/api/v1/companies/{company_id}/tasks",
        headers={"X-User-ID": res_id},
        json={
            "agent_instance_id": agent_id,
            "title": "Try",
            "instruction": "hello",
            "mode": "consult",
        },
    )
    assert denied.status_code == 403, denied.text

    grant = client.post(
        f"/api/v1/companies/{company_id}/agents/access/grant-operational",
        headers=_hdrs,
        json={},
    )
    assert grant.status_code == 200, grant.text
    assert grant.json()["granted"] >= 1

    ok = client.post(
        f"/api/v1/companies/{company_id}/tasks",
        headers={"X-User-ID": res_id},
        json={
            "agent_instance_id": agent_id,
            "title": "After grant",
            "instruction": "hello",
            "mode": "consult",
        },
    )
    assert ok.status_code in (200, 201), ok.text


def test_access_ui_markers():
    html = client.get("/workspace").content
    assert b"btnGrantOperationalAccess" in html
    assert b"accessAgentSelect" in html
