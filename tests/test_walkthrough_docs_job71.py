"""Job 71 — product walkthrough docs and notifications copy."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_walkthrough_doc_exists():
    p = Path("docs/features/00_PRODUCT_WALKTHROUGH.md")
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "Company profile" in text
    assert "Hire" in text
    assert "Tasks" in text


def test_notifications_view_has_notice():
    html = client.get("/workspace").text
    assert 'id="view-notifications"' in html
    assert "Notifications" in html
