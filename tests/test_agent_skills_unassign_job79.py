"""Job 79 — agent assigned skills + unassign UI markers."""
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


def test_unassign_helpers_in_js():
    text = JS.read_text(encoding="utf-8")
    assert "loadAgentAssignedSkills" in text
    assert "btn-unassign-skill" in text
    assert "/skills/${assignmentId}" in text or "/skills/${assignment_id}" in text or "skills/${assignmentId}" in text
    # DELETE used for unassign
    assert 'method: "DELETE"' in text or "method: 'DELETE'" in text


def test_assigned_list_in_html():
    text = HTML.read_text(encoding="utf-8")
    assert "skillAssignedList" in text
    assert "skillAssignedWrap" in text


def test_assign_refreshes_assigned(client):
    text = JS.read_text(encoding="utf-8")
    assert "loadAgentAssignedSkills" in text
    # after assign success should refresh
    assert "Skill assigned." in text
