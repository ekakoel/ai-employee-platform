"""Job 72 — marketplace/skills/policies UI + docs."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_marketplace_skills_policies_markup():
    html = client.get("/workspace").text
    assert 'id="view-marketplace"' in html
    assert 'id="view-skills"' in html
    assert 'id="skillCreateCard"' in html
    assert 'id="view-policy-management"' in html
    assert 'id="policyCreateCard"' in html


def test_docs_exist():
    assert Path("docs/features/14_marketplace_skills.md").is_file()
    assert Path("docs/features/15_policies_ai_admin.md").is_file()


def test_js_gating_hooks():
    js = Path("app/static/workspace/app.js").read_text(encoding="utf-8")
    assert "canInstall" in js
    assert "skillCreateCard" in js
    assert "policyCreateCard" in js
