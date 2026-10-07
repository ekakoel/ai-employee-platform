"""Phase 8 + Job 12 — Human workspace UI smoke tests."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_workspace_page_served():
    res = client.get("/workspace")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
    assert b"AI Employee Workspace" in res.content


def test_job12_nav_surfaces_present():
    """Job 12: task center, approval center, AI inbox, agent dashboard, workforce."""
    html = client.get("/workspace").content
    assert b"Workforce Overview" in html
    assert b"AI Inbox" in html
    assert b"Task Center" in html
    assert b"Approval Center" in html
    assert b"Agent Dashboard" in html
    assert b'data-view="workforce"' in html
    assert b'data-view="inbox"' in html
    assert b'data-view="tasks"' in html
    assert b'data-view="approvals"' in html
    assert b'data-view="agents"' in html


def test_workspace_assets_css_js():
    css = client.get("/workspace/assets/styles.css")
    assert css.status_code == 200
    assert b"--accent" in css.content

    js = client.get("/workspace/assets/app.js")
    assert js.status_code == 200
    assert b"loadInbox" in js.content
    assert b"loadWorkforce" in js.content
    assert b"btnConsult" in js.content or b"consult" in js.content
    assert b"delegation" in js.content
    assert b"automations" in js.content


def test_health_mentions_workspace():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json().get("workspace") == "/workspace"


def test_static_files_exist_on_disk():
    root = Path(__file__).resolve().parents[1] / "app" / "static" / "workspace"
    assert (root / "index.html").is_file()
    assert (root / "styles.css").is_file()
    assert (root / "app.js").is_file()
