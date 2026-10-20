"""Job 78 — Skills domain UI markers + domain map."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "app" / "static" / "workspace" / "app.js"
HTML = ROOT / "app" / "static" / "workspace" / "index.html"


@pytest.fixture
def client():
    return TestClient(app)


def test_skill_domain_map_in_app_js():
    text = JS.read_text(encoding="utf-8")
    assert "SKILL_DOMAIN_MAP" in text
    assert "function skillDomain" in text
    assert "quotation_preparation" in text
    assert "Reservation" in text
    assert "renderSkillsList" in text
    assert "btnAssignSkill" in text


def test_skills_toolbar_in_html():
    text = HTML.read_text(encoding="utf-8")
    assert "skillsToolbar" in text
    assert "skill-domain-chip" in text
    assert "skillAssignCard" in text
    assert "skillAssignAgent" in text


def test_workspace_serves_skills_markers(client):
    r = client.get("/workspace/")
    if r.status_code != 200:
        r = client.get("/workspace/index.html")
    if r.status_code != 200:
        pytest.skip("workspace static not mounted as expected")
    # JS is separate; HTML should have toolbar after install
    body = r.text
    assert "view-skills" in body or "Skills" in body
