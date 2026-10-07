"""Phase 8 — Workspace UI smoke tests."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_workspace_page_served():
    res = client.get("/workspace")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
    assert b"AI Employee Workspace" in res.content
    assert b"Task Center" in res.content
    assert b"Approvals" in res.content


def test_workspace_assets_css_js():
    css = client.get("/workspace/assets/styles.css")
    assert css.status_code == 200
    assert b"--accent" in css.content

    js = client.get("/workspace/assets/app.js")
    assert js.status_code == 200
    assert b"btnConsult" in js.content or b"consult" in js.content


def test_health_mentions_workspace():
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body.get("workspace") == "/workspace"


def test_static_files_exist_on_disk():
    root = Path(__file__).resolve().parents[1] / "app" / "static" / "workspace"
    assert (root / "index.html").is_file()
    assert (root / "styles.css").is_file()
    assert (root / "app.js").is_file()
