"""Job 49 — reservation demo playbook API."""

import uuid

from fastapi.testclient import TestClient

from tests.helpers import owner_setup, provision_company, bootstrap_demo, login_headers

from app.main import app
from app.tools.connectors import MockExternalSystemClient, set_external_client

client = TestClient(app)


def test_playbook_creates_task_and_auto_hires():
    set_external_client(MockExternalSystemClient())
    suffix = uuid.uuid4().hex[:8]
    # auth-hardened: demo bootstrap instead of public company create
    _cid, _oid, _hdrs, _demo = provision_company(client)
    co = {"id": _cid}
    owner = {"id": _oid, "email": _demo.get("owner_email")}
    headers = _hdrs
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
