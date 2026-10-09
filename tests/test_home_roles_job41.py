"""Job 41 — role-aware home command center markers."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]


def test_home_js_role_quick_actions():
    js = (ROOT / "app/static/workspace/home.js").read_text(encoding="utf-8")
    assert "roleQuickActions" in js
    assert "reservation" in js
    assert "Ask availability" in js or "Run reservation task" in js
    assert "/inventory" in js
    assert "demo/seed-reservation" in js


def test_home_html_sections():
    html = client.get("/workspace").content
    assert b"homeQuickActions" in html
    assert b"homeInventoryStatus" in html
    assert b"btnHomeRefreshInventory" in html


def test_home_quick_css():
    css = (ROOT / "app/static/workspace/styles.css").read_text(encoding="utf-8")
    assert "home-quick-grid" in css
