"""Phase 8 + Job 12 + Workspace v1 — Human workspace UI smoke tests."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_workspace_page_served():
    res = client.get("/workspace")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
    assert b"AI Employee Workspace" in res.content or b"AI Employee Platform" in res.content


def test_v1_nav_surfaces_present():
    """v1 product shell: home, inbox, chat, tasks, approvals, agents, marketplace."""
    html = client.get("/workspace").content
    assert b"AI Inbox" in html or b"Inbox" in html
    assert b"data-view=\"inbox\"" in html
    assert b"data-view=\"tasks\"" in html
    assert b"data-view=\"approvals\"" in html
    assert b"data-view=\"agents\"" in html
    assert b"data-view=\"chat\"" in html
    assert b"data-view=\"marketplace\"" in html
    assert b"data-view=\"home\"" in html
    assert b"loginGate" in html or b"Quick start" in html
    assert b"data-view=\"policies\"" in html
    assert b"data-view=\"tools\"" in html
    assert b"data-view=\"integrations\"" in html
    assert b"data-view=\"workflows\"" in html
    assert b"data-view=\"cost\"" in html
    assert b"data-view=\"scopecheck\"" in html


def test_workspace_assets_css_js():
    css = client.get("/workspace/assets/styles.css")
    assert css.status_code == 200
    assert b"--accent" in css.content

    js = client.get("/workspace/assets/app.js")
    assert js.status_code == 200
    assert b"loadInbox" in js.content
    assert b"loadHome" in js.content
    assert b"loadMarketplace" in js.content
    assert b"loadTools" in js.content
    assert b"loadIntegrations" in js.content
    assert b"loadCost" in js.content
    assert b"btnSimulate" in js.content
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
