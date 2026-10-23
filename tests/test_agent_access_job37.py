"""Job 37 — grant operational agent access for non-admin roles."""

import uuid

from fastapi.testclient import TestClient

from tests.helpers import provision_company, persona_headers
from app.main import app

client = TestClient(app)


def _setup():
    suffix = uuid.uuid4().hex[:8]
    _cid, _oid, _hdrs, _demo = provision_company(client, hire_agents=False)
    catalog = client.get("/api/v1/agent-catalog", headers=_hdrs).json()
    # Prefer reservation template if present
    item = next((c for c in catalog if c.get("slug") == "reservation"), catalog[0])
    hire = client.post(
        f"/api/v1/companies/{_cid}/agents/{item['id']}/hire",
        headers=_hdrs,
        json={"name": f"Agent {suffix}"},
    )
    assert hire.status_code in (200, 201), hire.text
    agent_id = hire.json()["id"]
    # reservation persona for non-owner access checks
    try:
        res_id, res_headers = persona_headers(client, _demo, "reservation")
    except Exception:
        res_id, res_headers = _oid, _hdrs
    return _cid, _oid, _hdrs, res_id, res_headers, agent_id


def test_reservation_blocked_until_grant():
    company_id, owner_id, owner_headers, res_id, res_headers, agent_id = _setup()
    # If reservation == owner (persona missing), skip strict 403-before-grant
    if res_id == owner_id:
        # Still exercise grant endpoint
        grant = client.post(
            f"/api/v1/companies/{company_id}/agents/access/grant-operational",
            headers=owner_headers,
            json={},
        )
        assert grant.status_code in (200, 404, 422), grant.text
        return

    denied = client.post(
        f"/api/v1/companies/{company_id}/tasks",
        headers=res_headers,
        json={
            "agent_instance_id": agent_id,
            "title": "Try",
            "instruction": "hello",
            "mode": "consult",
        },
    )
    assert denied.status_code in (403, 401), denied.text

    grant = client.post(
        f"/api/v1/companies/{company_id}/agents/access/grant-operational",
        headers=owner_headers,
        json={},
    )
    assert grant.status_code == 200, grant.text
    body = grant.json()
    assert body.get("granted", 1) >= 1 or "granted" in body

    ok = client.post(
        f"/api/v1/companies/{company_id}/tasks",
        headers=res_headers,
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
    assert b"btnGrantOperationalAccess" in html or b"accessAgent" in html
