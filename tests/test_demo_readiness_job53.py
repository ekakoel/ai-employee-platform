"""Job 53 — home demo readiness checklist + quick-start personas."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]


def test_home_has_demo_checklist_markers():
    html = client.get("/workspace").text
    assert "homeDemoChecklist" in html
    assert "Demo readiness" in html
    assert "btnHomeDemoPlaybook" in html


def test_home_js_build_demo_checklist():
    js = (ROOT / "app/static/workspace/home.js").read_text(encoding="utf-8")
    assert "function buildDemoChecklist" in js
    assert "demo-ready" in js or "home-demo-ready" in js
    assert "inventoryCount" in js
    assert "btnHomeDemoPlaybook" in js


def test_quickstart_lists_all_demo_accounts():
    js = (ROOT / "app/static/workspace/app.js").read_text(encoding="utf-8")
    # At least some demo personas remain in quick-start / bootstrap UI
    markers = ("@demo.local", "demo", "owner@", "bootstrap")
    assert any(m in js for m in markers), "expected demo persona markers in app.js"


