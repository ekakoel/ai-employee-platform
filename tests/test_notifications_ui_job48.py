"""Job 48 — actionable notifications UI markers."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]


def test_notifications_js_actionable():
    js = (ROOT / "app/static/workspace/app.js").read_text(encoding="utf-8")
    assert "notificationTarget" in js
    assert "btn-notif-open" in js
    assert "n.title" in js or "n.title ||" in js
    assert "markNotificationRead" in js


def test_notifications_html_filter():
    html = client.get("/workspace").text
    assert "notifFilter" in html


def test_notif_unread_css():
    css = (ROOT / "app/static/workspace/styles.css").read_text(encoding="utf-8")
    assert "notif-unread" in css
