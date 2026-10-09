"""Job 42 — login gate bootstrap: quick start + create company visible."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_workspace_shows_quick_start_and_create_company():
    html = client.get("/workspace").text
    assert "btnQuickStart" in html
    assert 'data-tab="quick"' in html
    assert "btnCreateCompany" in html
    assert "newCompanyName" in html
    # quick tab button should not carry developer-only
    assert 'class="tab developer-only" data-tab="quick"' not in html


def test_create_company_then_register_login_api():
    import uuid

    name = f"Bootstrap Co {uuid.uuid4().hex[:8]}"
    co = client.post("/api/v1/companies", json={"name": name})
    assert co.status_code in (200, 201), co.text
    company_id = co.json()["id"]
    email = f"owner-{uuid.uuid4().hex[:6]}@bootstrap.test"
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "company_id": company_id,
            "email": email,
            "name": "Owner",
            "password": "demo12345",
            "role": "owner",
        },
    )
    assert reg.status_code in (200, 201), reg.text
    login = client.post(
        "/api/v1/auth/login",
        json={"company_id": company_id, "email": email, "password": "demo12345"},
    )
    assert login.status_code == 200, login.text
    assert login.json().get("access_token")
