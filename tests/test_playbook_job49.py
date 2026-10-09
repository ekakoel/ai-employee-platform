"""Job 49 — reservation demo playbook API."""

import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.tools.connectors import MockExternalSystemClient, set_external_client

client = TestClient(app)


def test_playbook_creates_task_and_auto_hires():
    set_external_client(MockExternalSystemClient())
    suffix = uuid.uuid4().hex[:8]
    co = client.post("/api/v1/companies", json={"name": f"PB {suffix}"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={
            "name": "Owner",
            "email": f"owner-{suffix}@pb49.test",
            "role": "owner",
            "password": "demo12345",
        },
    ).json()
    headers = {"X-User-ID": owner["id"]}
    res = client.post(
        f"/api/v1/companies/{co['id']}/demo/playbook-reservation",
        headers=headers,
        json={},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("task_id"), body
    assert body.get("agent_instance_id"), body
    tasks = client.get(f"/api/v1/companies/{co['id']}/tasks", headers=headers).json()
    assert any(t["id"] == body["task_id"] for t in tasks)
    agents = client.get(f"/api/v1/companies/{co['id']}/agents", headers=headers).json()
    assert len(agents) >= 1


def test_playbook_markers_in_ui():
    html = client.get("/workspace").text
    assert "btnDemoPlaybook" in html or "btnInvPlaybook" in html or "playbook" in html.lower()
