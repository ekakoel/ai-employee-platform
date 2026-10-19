"""Job 68 — tasks/approvals UI gating and docs."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_tasks_view_has_create_card():
    html = client.get("/workspace").text
    assert 'id="view-tasks"' in html
    assert 'id="taskCreateCard"' in html
    assert "btnCreateTask" in html
    assert 'id="view-approvals"' in html


def test_js_task_and_approval_gating():
    js = Path("app/static/workspace/app.js").read_text(encoding="utf-8")
    assert "applyTaskActionGating" in js
    assert "approval.manage" in js
