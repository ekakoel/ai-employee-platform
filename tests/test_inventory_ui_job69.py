"""Job 69 — inventory UI gating."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_inventory_view_structure():
    html = client.get("/workspace").text
    assert 'id="view-inventory"' in html
    assert 'id="inventoryActionsCard"' in html
    assert "btnInvSeed" in html


def test_inventory_gating_js():
    js = Path("app/static/workspace/app.js").read_text(encoding="utf-8")
    assert "applyInventoryGating" in js
