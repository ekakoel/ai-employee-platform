"""Job 58 — email+password login, forgot password (auth-hardened fixtures)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _bootstrap_owner():
    res = client.post("/api/v1/demo/bootstrap")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("owner_email")
    assert body.get("company_id")
    return body


def test_login_email_password_only():
    demo = _bootstrap_owner()
    res = client.post(
        "/api/v1/auth/login",
        json={"email": demo["owner_email"], "password": "demo12345"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["email"] == demo["owner_email"]
    assert body["company_id"] == demo["company_id"]
    assert body.get("access_token")


def test_workspace_login_standards_and_company_register():
    """Public self-signup of employees is gone; company registration remains."""
    html = client.get("/workspace").text
    assert "btnToggleLoginPassword" in html
    assert "btnForgotPassword" in html or "/forgot-password" in html
    assert "loginEmail" in html
    assert "loginPassword" in html
    # Company onboarding (not free employee register without invite)
    assert "Register company" in html
    assert "Register to company" not in html


def test_forgot_and_reset_password_debug_token():
    demo = _bootstrap_owner()
    # Use a non-owner persona so we don't disturb owner login semantics
    member = next((u for u in demo.get("users") or [] if u.get("role") == "member"), None)
    if member is None:
        member = next(u for u in demo["users"] if u["role"] != "owner")
    email = member["email"]

    forgot = client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert forgot.status_code == 200
    data = forgot.json()
    assert "message" in data
    token = data.get("reset_token")
    if not token:
        # Production-like: no token in body — still OK
        return
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
