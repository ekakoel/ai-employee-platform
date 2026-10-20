"""Job 81 — skills dedupe wired into renderSkillsList."""
from pathlib import Path

JS = Path(__file__).resolve().parents[1] / "app" / "static" / "workspace" / "app.js"


def test_dedupe_helper():
    text = JS.read_text(encoding="utf-8")
    assert "function dedupeSkillsPreferCompany" in text


def test_render_calls_dedupe():
    text = JS.read_text(encoding="utf-8")
    assert "const deduped = dedupeSkillsPreferCompany(list)" in text
    # filtered must use deduped, not raw list for "all"
    assert '? deduped' in text or "? deduped\n" in text or " ? deduped" in text
