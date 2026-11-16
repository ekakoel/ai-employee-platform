"""Job 54 — smoke E2E under locked auth (bootstrap + Bearer)."""

from __future__ import annotations

import io

from fastapi.testclient import TestClient

from app.main import app
from app.tools.connectors import MockExternalSystemClient, set_external_client

client = TestClient(app)


def _fresh_company():
    set_external_client(MockExternalSystemClient())
    demo = client.post("/api/v1/demo/bootstrap")
    assert demo.status_code == 200, demo.text
    body = demo.json()
    company_id = body["company_id"]
    login = client.post(
        "/api/v1/auth/login",
        json={"email": body["owner_email"], "password": "demo12345"},
    )
    assert login.status_code == 200, login.text
    tok = login.json()
    headers = {
        "Authorization": f"Bearer {tok['access_token']}",
        "X-User-ID": tok["user_id"],
    }
    return company_id, headers, body["owner_email"]


def test_smoke_playbook_execute_knowledge_inventory():
    company_id, headers, demo_body = _fresh_company()

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

    ex = client.post(
        f"/api/v1/companies/{company_id}/tasks/{task_id}/execute",
        headers=headers,
        json={},
    )
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

    content = (
        "Partnership contract. Alila Hotel rate IDR 1850000. "
        "Valid through 2026-12-31. Breakfast included."
    ).encode()
    ing = client.post(
        f"/api/v1/companies/{company_id}/knowledge/ingest-extract",
        headers=headers,
        files={"file": ("alila-contract.txt", io.BytesIO(content), "text/plain")},
        data={"title": "Alila contract smoke", "category": "document"},
    )
    assert ing.status_code == 201, ing.text
    know = ing.json()
    assert "Alila" in know["content"]

    # New sources are not visible to retrieval/listing until a separate
    # administrator approves a purpose-bound source grant.
    agent_id = body["agent_instance_id"]
    listed = client.get(
        f"/api/v1/companies/{company_id}/knowledge",
        headers=headers,
        params={"agent_instance_id": agent_id},
    )
    assert listed.status_code == 200
    assert not any(k["id"] == know["id"] for k in listed.json())

    approver = next(
        (u for u in (demo_body.get("users") or []) if u.get("role") == "ai_admin"),
        None,
    )
    assert approver is not None, "demo bootstrap must include an independent AI admin"
    manager_login = client.post(
        "/api/v1/auth/login",
        json={"email": approver["email"], "password": "demo12345"},
    )
    assert manager_login.status_code == 200, manager_login.text
    manager_token = manager_login.json()
    manager_headers = {
        "Authorization": f"Bearer {manager_token['access_token']}",
        "X-User-ID": manager_token["user_id"],
    }
    created_grant = client.post(
        f"/api/v1/companies/{company_id}/knowledge/source-grants",
        headers=manager_headers,
        json={
            "source_type": "item",
            "source_id": know["id"],
            "classification": "B",
            "owner_user_id": manager_token["user_id"],
            "allowed_user_ids": [headers["X-User-ID"]],
            "allowed_purposes": ["knowledge_list", "knowledge_search", "task_execution"],
        },
    )
    assert created_grant.status_code == 201, created_grant.text
    approved_grant = client.post(
        f"/api/v1/companies/{company_id}/knowledge/source-grants/{created_grant.json()['id']}/approve",
        headers=headers,
    )
    assert approved_grant.status_code == 200, approved_grant.text

    listed = client.get(
        f"/api/v1/companies/{company_id}/knowledge",
        headers=headers,
        params={"agent_instance_id": agent_id},
    )
    assert listed.status_code == 200
    assert any(k["id"] == know["id"] for k in listed.json())

    ws = client.get("/workspace")
    assert ws.status_code == 200


def test_demo_script_file_present():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    doc = root / "docs" / "DEMO_15MIN.md"
    assert doc.exists(), "docs/DEMO_15MIN.md missing"
    text = doc.read_text(encoding="utf-8")
    assert "playbook" in text.lower() or "demo" in text.lower()
