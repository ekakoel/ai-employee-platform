"""Job 43 — chat → task bridge UX markers and reply footer."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]


def test_chat_html_run_task_controls():
    html = client.get("/workspace").text
    assert "chatRunTask" in html
    assert "Also create Task" in html
    assert "chatTaskHint" in html


def test_chat_js_run_handler():
    js = (ROOT / "app/static/workspace/chat.js").read_text(encoding="utf-8")
    assert "chatRunTask" in js
    assert "/tasks/" in js and "/consult" in js
    assert "/execute" in js


def test_conversation_footer_mentions_task():
    text = (ROOT / "app/services/conversation.py").read_text(encoding="utf-8")
    assert "Task created" in text
    assert "Chat still does" in text or "does **not** run tools" in text
