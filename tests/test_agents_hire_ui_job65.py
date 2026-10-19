"""Job 65 — AI Employee hire UI gating."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_hire_card_and_gating_in_workspace():
    html = client.get("/workspace").text
    assert 'id="hireCard"' in html
    assert "btnHire" in html
    assert "catalogSelect" in html
    js = Path("app/static/workspace/app.js").read_text(encoding="utf-8")
    assert "applyAgentActionGating" in js
    assert "agent.hire" in js


def test_owner_can_hire_from_catalog():
    demo = client.post("/api/v1/demo/bootstrap")
    assert demo.status_code == 200, demo.text
    body = demo.json()
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
    catalog = client.get("/api/v1/agent-catalog", headers=headers)
    assert catalog.status_code == 200, catalog.text
    items = catalog.json()
    if not items:
        return
    cid = items[0]["id"]
    hire = client.post(
        f"/api/v1/companies/{body['company_id']}/agents/{cid}/hire",
        headers=headers,
        json={"name": "UI Hire Test Agent"},
    )
    assert hire.status_code in (200, 201), hire.text
