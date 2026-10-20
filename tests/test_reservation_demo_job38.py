"""Job 38 — demo reservation inventory + range availability matching."""

import uuid

from fastapi.testclient import TestClient

from tests.helpers import owner_setup, provision_company, bootstrap_demo, login_headers

from app.main import app
from app.tools.base import ToolContext
from app.tools.connectors import MockExternalSystemClient, set_external_client
from app.tools.domain import availability_records

client = TestClient(app)


def test_range_availability_matches_requested_stay():
    set_external_client(MockExternalSystemClient())
    from app.services.demo_reservation import seed_demo_availability

    company_id = "co-demo-range"
    seed_demo_availability(company_id)
    ctx = ToolContext(
        company_id=company_id,
        agent_instance_id="agent-1",
        task_id=None,
    )
    rows = availability_records(
        ctx,
        {
            "check_in": "2026-10-27",
            "check_out": "2026-10-28",
            "guests": 2,
            "location": "Alila",
        },
    )
    assert len(rows) >= 1
    assert all(r["check_in"] == "2026-10-27" for r in rows)
    assert all(r["company_id"] == company_id for r in rows)
    assert any(r.get("room_type") == "Deluxe Double" for r in rows)


def test_seed_reservation_api_and_search_via_domain():
    """Seed via API, verify inventory through domain matching (no policy gate)."""
    set_external_client(MockExternalSystemClient())
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
    body = seed.json()
    assert body["availability_count"] >= 3
    assert body.get("knowledge_id")

    ctx = ToolContext(
        company_id=co["id"],
        agent_instance_id="any",
        task_id=None,
    )
    rows = availability_records(
        ctx,
        {
            "check_in": "2026-10-30",
            "check_out": "2026-10-31",
            "guests": 2,
            "location": "Alila Hotel",
        },
    )
    assert len(rows) >= 1
    assert any(int(r.get("rate") or 0) > 0 for r in rows)


def test_search_tool_with_allow_policy():
    """Full tool execute path after allowing search_availability by policy."""
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
    pol = client.post(
        f"/api/v1/companies/{co['id']}/policies",
        headers=_hdrs,
        json={
            "name": f"Allow search availability {suffix}",
            "configuration": {
                "tool": "search_availability",
                "effect": "allow",
                "priority": 5,
            },
            "is_active": True,
        },
    )
    assert pol.status_code in (200, 201), pol.text

    catalog = client.get("/api/v1/agent-catalog").json()
    reservation = next(
        (c for c in catalog if "reservation" in (c.get("slug") or "")),
        catalog[0],
    )
    hire = client.post(
        f"/api/v1/companies/{co['id']}/agents/{reservation['id']}/hire",
        headers=_hdrs,
        json={"name": "Res AI"},
    )
    assert hire.status_code in (200, 201), hire.text
    agent_id = hire.json()["id"]

    tool = client.post(
        f"/api/v1/companies/{co['id']}/agents/{agent_id}/tools/search_availability/execute",
        headers=_hdrs,
        json={
            "arguments": {
                "check_in": "2026-10-30",
                "check_out": "2026-10-31",
                "guests": 2,
                "location": "Alila Hotel",
            }
        },
    )
    assert tool.status_code == 200, tool.text


def test_ui_has_seed_button():
    html = client.get("/workspace").content
    assert b"btnSeedReservationDemo" in html
