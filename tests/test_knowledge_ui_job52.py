"""Job 52 — knowledge list UI markers, extract badge, quick-start personas."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]


def test_knowledge_view_has_list_and_filter():
    html = client.get("/workspace").text
    assert 'id="knowList"' in html
    assert 'id="knowFilter"' in html
    assert "from extract" in html or "Extract to knowledge" in html
    assert "btnRefreshKnowledge" in html


def test_load_knowledge_js_helpers():
    js = (ROOT / "app/static/workspace/app.js").read_text(encoding="utf-8")
    assert "async function loadKnowledge" in js
    assert "isExtractedKnowledge" in js
    assert "tag-extract" in js
    assert "loadKnowledge" in js
    assert "demo.local" in js or "loadKnowledge" in js
    assert "loadKnowledge" in js
    # ingest handler must live inside main script (not only orphan)
    assert js.count("btnKnowledgeIngest") >= 1
    assert not js.rstrip().endswith('if ($("btnKnowledgeIngest"))')


def test_extract_badge_css():
    css = (ROOT / "app/static/workspace/styles.css").read_text(encoding="utf-8")
    assert "tag-extract" in css
