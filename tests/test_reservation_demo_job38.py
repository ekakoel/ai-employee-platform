"""Job 38 — demo reservation inventory + range availability matching."""

import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.tools.connectors import MockExternalSystemClient, set_external_client
from app.tools.domain import availability_records
from app.tools.base import ToolContext

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
        user_id=None,
        db=None,
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


def test_seed_reservation_api_and_search_tool():
    set_external_client(MockExternalSystemClient())
    suffix = uuid.uuid4().hex[:8]
    co = client.post("/api/v1/companies", json={"name": f"Co38 {suffix}"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={
            "name": "Owner",
            "email": f"owner-{suffix}@job38.test",
            "role": "owner",
            "password": "demo12345",
        },
    ).json()
    seed = client.post(
        f"/api/v1/companies/{co['id']}/demo/seed-reservation",
        headers={"X-User-ID": owner["id"]},
        json={},
    )
    assert seed.status_code == 200, seed.text
    body = seed.json()
    assert body["availability_count"] >= 3
    assert body.get("knowledge_id")

    catalog = client.get("/api/v1/agent-catalog").json()
    reservation = next((c for c in catalog if "reservation" in c.get("slug", "")), catalog[0])
    hire = client.post(
        f"/api/v1/companies/{co['id']}/agents/{reservation['id']}/hire",
        headers={"X-User-ID": owner["id"]},
        json={"name": "Res AI"},
    )
    assert hire.status_code in (200, 201), hire.text
    agent_id = hire.json()["id"]

    tool = client.post(
        f"/api/v1/companies/{co['id']}/agents/{agent_id}/tools/search_availability/execute",
        headers={"X-User-ID": owner["id"]},
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
    data = tool.json()
    # tool executor may wrap result
    payload = data.get("result") or data.get("output") or data
    if isinstance(payload, dict) and "count" in payload:
        assert payload["count"] >= 1
    else:
        # accept nested structures
        text = str(data)
        assert "Deluxe" in text or "Alila" in text or "options" in text


def test_ui_has_seed_button():
    html = client.get("/workspace").content
    assert b"btnSeedReservationDemo" in html
