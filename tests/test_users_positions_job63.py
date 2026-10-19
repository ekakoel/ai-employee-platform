"""Job 63 — users & job positions."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_app_js_syntax_btn_refresh_users():
    js = Path("app/static/workspace/app.js").read_text(encoding="utf-8")
    assert 'if ($("btnRefreshUsers")) $("btnRefreshUsers").onclick = loadUsers;' in js
    assert 'if ($("btnRefreshUsers") $("btnRefreshUsers")' not in js


def test_users_view_has_positions_ui():
    html = client.get("/workspace").text
    assert "userRoleInput" in html or "job position" in html.lower() or "Job position" in html
