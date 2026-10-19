"""Job 67 — chat advisory UI copy and module."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_chat_view_advisory_notice():
    html = client.get("/workspace").text
    assert 'id="view-chat"' in html
    assert "Advisory" in html or "advisory" in html.lower()
    assert "chatCreateTask" in html
    assert "chatTyping" in html


def test_chat_js_task_gating():
    js = Path("app/static/workspace/chat.js").read_text(encoding="utf-8")
    assert "task.create" in js
    assert "chatTyping" in js
