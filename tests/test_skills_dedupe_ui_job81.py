"""Job 81 — skills catalog dedupe prefer company."""
from __future__ import annotations

from pathlib import Path

JS = Path(__file__).resolve().parents[1] / "app" / "static" / "workspace" / "app.js"


def test_dedupe_helper_present():
    text = JS.read_text(encoding="utf-8")
    assert "function dedupeSkillsPreferCompany" in text
    assert "dedupeSkillsPreferCompany" in text


def test_render_uses_dedupe():
    text = JS.read_text(encoding="utf-8")
    assert "dedupeSkillsPreferCompany(_skillsCache)" in text or "dedupeSkillsPreferCompany(list)" in text
