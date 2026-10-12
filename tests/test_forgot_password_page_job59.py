"""Job 59 — dedicated forgot-password page."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_forgot_password_page_serves():
    res = client.get("/forgot-password")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
    body = res.text
    assert "Forgot password" in body
    assert "/api/v1/auth/forgot-password" in body
    assert "Set new password" in body or "newPassword" in body


def test_reset_password_alias_serves():
    res = client.get("/reset-password")
    assert res.status_code == 200
    assert "Forgot password" in res.text or "password" in res.text.lower()


def test_login_links_to_forgot_page():
    html = client.get("/workspace").text
    assert "/forgot-password" in html
