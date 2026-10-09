"""Job 40 — results artifact surface markers in workspace assets."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]


def test_results_js_has_artifact_extractors():
    js = (ROOT / "app/static/workspace/results.js").read_text(encoding="utf-8")
    assert "extractArtifacts" in js
    assert "draft_quotation" in js
    assert "search_availability" in js
    assert "renderArtifactCards" in js


def test_workspace_result_type_filters():
    html = client.get("/workspace").content
    assert b'value="quotation"' in html
    assert b'value="availability"' in html


def test_styles_artifact_card():
    css = (ROOT / "app/static/workspace/styles.css").read_text(encoding="utf-8")
    assert ".artifact-card" in css


def test_task_artifact_tags_helper():
    js = (ROOT / "app/static/workspace/app.js").read_text(encoding="utf-8")
    assert "function taskArtifactTags" in js
