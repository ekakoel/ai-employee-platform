"""Job 70 — home command center quick actions."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_home_and_inbox_markup():
    html = client.get("/workspace").text
    assert 'id="view-home"' in html
    assert 'id="homeQuickActions"' in html
    assert 'id="view-inbox"' in html
    assert "Setup path:" in html


def test_home_js_role_actions():
    js = Path("app/static/workspace/home.js").read_text(encoding="utf-8")
    assert "roleQuickActions" in js
    assert "contract_manager" in js
    assert "Users & positions" in js or "Invite staff" in js
