"""Job 58 — email+password login, no public register, forgot password."""

import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_login_email_password_only():
    suffix = uuid.uuid4().hex[:8]
    email = f"owner-{suffix}@login58.test"
    co = client.post("/api/v1/companies", json={"name": f"Login {suffix}"}).json()
    client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={
            "name": "Owner",
            "email": email,
            "role": "owner",
            "password": "demo12345",
        },
    )
    res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "demo12345"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["email"] == email
    assert body["company_id"] == co["id"]
    assert body.get("access_token")


def test_workspace_has_no_register_tab():
    html = client.get("/workspace").text
    assert 'data-tab="register"' not in html
    assert "btnToggleLoginPassword" in html
    assert "btnForgotPassword" in html
    assert "loginEmail" in html
    assert "loginPassword" in html


def test_forgot_and_reset_password_debug_token():
    suffix = uuid.uuid4().hex[:8]
    email = f"reset-{suffix}@login58.test"
    co = client.post("/api/v1/companies", json={"name": f"Reset {suffix}"}).json()
    client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={
            "name": "User",
            "email": email,
            "role": "member",
            "password": "oldpass12",
        },
    )
    forgot = client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert forgot.status_code == 200
    data = forgot.json()
    assert "message" in data
    token = data.get("reset_token")
    if token:
        reset = client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "new_password": "newpass99"},
        )
        assert reset.status_code == 200, reset.text
        login = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "newpass99"},
        )
        assert login.status_code == 200, login.text
