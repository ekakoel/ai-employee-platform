"""Job 60 — debug demo bootstrap; no Bearer token required."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app)


def test_bootstrap_status_no_auth():
    res = client.get("/api/v1/demo/bootstrap/status")
    assert res.status_code == 200
    body = res.json()
    assert body.get("auth_required") is False
    assert "allowed" in body


def test_demo_bootstrap_no_bearer():
    status = client.get("/api/v1/demo/bootstrap/status").json()
    res = client.post("/api/v1/demo/bootstrap")
    if not status.get("allowed"):
        assert res.status_code == 403
        return
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("owner_email")
    login = client.post(
        "/api/v1/auth/login",
        json={"email": body["owner_email"], "password": "demo12345"},
    )
    assert login.status_code == 200, login.text


def test_quickstart_js_uses_bootstrap():
    js = Path("app/static/workspace/app.js").read_text(encoding="utf-8")
    assert "/demo/bootstrap" in js
    i = js.find("btnQuickStart")
    chunk = js[i : i + 1500]
    assert "/demo/bootstrap" in chunk
