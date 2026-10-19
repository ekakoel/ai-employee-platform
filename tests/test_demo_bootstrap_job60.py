"""Job 60 — debug demo bootstrap for Quick start."""

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app)


def test_demo_bootstrap_requires_debug_or_succeeds_in_dev():
    res = client.post("/api/v1/demo/bootstrap")
    if not settings.debug:
        assert res.status_code == 403
        return
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("company_id")
    assert body.get("owner_email")
    assert body.get("password") == "demo12345"
    assert len(body.get("users") or []) >= 1

    login = client.post(
        "/api/v1/auth/login",
        json={"email": body["owner_email"], "password": "demo12345"},
    )
    assert login.status_code == 200, login.text
    assert login.json().get("access_token")


def test_quickstart_uses_bootstrap_endpoint():
    js = (client.get("/workspace").text)  # page loads
    from pathlib import Path
    app_js = Path("app/static/workspace/app.js").read_text(encoding="utf-8")
    assert "/demo/bootstrap" in app_js
    assert "Quick start failed" in app_js
