"""Job 80 — AI Employees skill chips + Manage skills markers."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "app" / "static" / "workspace" / "app.js"


@pytest.fixture
def client():
    return TestClient(app)


def test_open_agent_skills_helper():
    text = JS.read_text(encoding="utf-8")
    assert "function openAgentSkills" in text
    assert 'showView("skills")' in text
    assert "loadAgentAssignedSkills" in text


def test_agent_card_manage_skills_button():
    text = JS.read_text(encoding="utf-8")
    assert "btn-manage-skills" in text
    assert "Manage skills" in text


def test_agent_skill_chips_use_domain():
    text = JS.read_text(encoding="utf-8")
    # cards use skillDomain for chip coloring
    assert "skillDomain" in text
    assert "domainBadgeClass" in text
