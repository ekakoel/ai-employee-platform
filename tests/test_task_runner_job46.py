"""Job 46 — task list uses correct consult/execute endpoints."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]


def test_load_tasks_uses_consult_and_execute_paths():
    js = (ROOT / "app/static/workspace/app.js").read_text(encoding="utf-8")
    assert "/tasks/${id}/consult" in js or '/tasks/${id}/consult' in js
    assert "/tasks/${id}/execute" in js or "/tasks/${id}/execute" in js
    # Broken legacy path must be gone
    assert "/tasks/${b.dataset.id}/run" not in js
    assert "btn-run-consult" in js
    assert "Running…" in js or "Running..." in js


def test_no_duplicate_consult_action_block():
    js = (ROOT / "app/static/workspace/app.js").read_text(encoding="utf-8")
    # old template had nested duplicate Run consult for pending consult
    assert js.count("Run consult") <= 3
