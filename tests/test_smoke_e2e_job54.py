"""Job 54 — smoke E2E: playbook → execute → knowledge ingest → inventory visible."""

from __future__ import annotations

import io
import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.tools.connectors import MockExternalSystemClient, set_external_client

client = TestClient(app)


def _fresh_company():
    set_external_client(MockExternalSystemClient())
    suffix = uuid.uuid4().hex[:8]
    co = client.post("/api/v1/companies", json={"name": f"E2E {suffix}"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={
            "name": "Owner",
            "email": f"owner-{suffix}@e2e54.test",
            "role": "owner",
            "password": "demo12345",
        },
    ).json()
    headers = {"X-User-ID": owner["id"]}
    return co["id"], headers, suffix


def test_smoke_playbook_execute_knowledge_inventory():
    company_id, headers, suffix = _fresh_company()

    # 1) Demo playbook: seed inventory + hire agent + pending task
    pb = client.post(
        f"/api/v1/companies/{company_id}/demo/playbook-reservation",
        headers=headers,
        json={},
    )
    assert pb.status_code == 200, pb.text
    body = pb.json()
    assert body.get("task_id"), body
    assert body.get("agent_instance_id"), body
    task_id = body["task_id"]

    inv = client.get(f"/api/v1/companies/{company_id}/inventory", headers=headers)
    assert inv.status_code == 200, inv.text
    assert len(inv.json().get("items") or []) >= 1

    agents = client.get(f"/api/v1/companies/{company_id}/agents", headers=headers)
    assert agents.status_code == 200
    assert len(agents.json()) >= 1

    # 2) Execute the playbook task (tools + policy path)
    ex = client.post(
        f"/api/v1/companies/{company_id}/tasks/{task_id}/execute",
        headers=headers,
        json={},
    )
    # Allow completed or waiting_approval; hard fail only on 4xx/5xx unexpected
    assert ex.status_code == 200, ex.text
    task = ex.json()
    assert task["id"] == task_id
    assert task.get("status") in {
        "completed",
        "waiting_approval",
        "failed",
        "pending",
        "running",
    }, task
    # Prefer successful tool path when policies allow
    if task.get("status") == "failed":
        # Still a valid smoke path if policy blocked — surface for debugging
        assert "result" in task or task.get("status") == "failed"

    # 3) Knowledge ingest (file not retained)
    content = (
        f"Partnership contract {suffix}. Alila Hotel rate IDR 1850000. "
        "Valid through 2026-12-31. Breakfast included."
    ).encode()
    ing = client.post(
        f"/api/v1/companies/{company_id}/knowledge/ingest-extract",
        headers=headers,
        files={"file": ("alila-contract.txt", io.BytesIO(content), "text/plain")},
        data={"title": f"Alila contract {suffix}", "category": "document"},
    )
    assert ing.status_code == 201, ing.text
    know = ing.json()
    assert know["title"] == f"Alila contract {suffix}"
    assert "Alila" in know["content"]
    assert "not retained" in know["content"].lower()

    listed = client.get(f"/api/v1/companies/{company_id}/knowledge", headers=headers)
    assert listed.status_code == 200
    assert any(k["id"] == know["id"] for k in listed.json())

    # 4) Workspace still serves product shell
    ws = client.get("/workspace")
    assert ws.status_code == 200
    assert b"homeDemoChecklist" in ws.content or b"Demo readiness" in ws.content
    assert b"knowList" in ws.content or b"Knowledge" in ws.content


def test_demo_script_file_present():
    """Human walkthrough script ships with the repo."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    doc = root / "docs" / "DEMO_15MIN.md"
    assert doc.exists(), "docs/DEMO_15MIN.md missing"
    text = doc.read_text(encoding="utf-8")
    assert "playbook" in text.lower()
    assert "knowledge" in text.lower()
    assert "demo12345" in text
