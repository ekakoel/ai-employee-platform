"""Job 66 — knowledge UI write gating and extract form."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_knowledge_view_structure():
    html = client.get("/workspace").text
    assert 'id="view-knowledge"' in html
    assert 'id="knowledgeWriteCard"' in html
    assert "btnKnowledgeIngest" in html
    assert "knowledgeIngestCategory" in html


def test_knowledge_gating_in_js():
    js = Path("app/static/workspace/app.js").read_text(encoding="utf-8")
    assert "applyKnowledgeWriteGating" in js
    assert "knowledge.write" in js


def test_owner_can_add_knowledge_note():
    demo = client.post("/api/v1/demo/bootstrap")
    assert demo.status_code == 200, demo.text
    body = demo.json()
    login = client.post(
        "/api/v1/auth/login",
        json={"email": body["owner_email"], "password": "demo12345"},
    )
    assert login.status_code == 200
    tok = login.json()
    headers = {
        "Authorization": f"Bearer {tok['access_token']}",
        "X-User-ID": tok["user_id"],
    }
    res = client.post(
        f"/api/v1/companies/{body['company_id']}/knowledge",
        headers=headers,
        json={
            "title": "Leave policy",
            "content": "Employees get 12 days annual leave.",
            "category": "policy",
        },
    )
    assert res.status_code in (200, 201), res.text
