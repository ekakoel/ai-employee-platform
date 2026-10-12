"""Job 55 — CI workflow present and covers smoke E2E."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_github_actions_ci_workflow_exists():
    path = ROOT / ".github" / "workflows" / "ci.yml"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "pytest" in text
    assert "test-sqlite" in text or "Pytest (SQLite)" in text
    assert "test_smoke_e2e_job54" in text
    assert "concurrency" in text
    assert "cache: pip" in text or "cache: 'pip'" in text


def test_pytest_ini_excludes_integration_marker_defined():
    ini = (ROOT / "pytest.ini").read_text(encoding="utf-8")
    assert "integration" in ini
