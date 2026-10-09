"""Job 47 — approvals center uses /approve and /reject."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]


def test_approvals_js_correct_endpoints():
    js = (ROOT / "app/static/workspace/app.js").read_text(encoding="utf-8")
    assert "/approvals/${b.dataset.id}/approve" in js or '/approvals/${b.dataset.id}/approve' in js
    assert "/reject" in js
    assert "/approvals/${b.dataset.id}/review" not in js
    assert "btn-approve" in js
    assert "approvalPayloadSummary" in js


def test_approvals_html_filter():
    html = client.get("/workspace").text
    assert "approvalFilter" in html
    assert "approvalStats" in html
