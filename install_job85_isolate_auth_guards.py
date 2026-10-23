#!/usr/bin/env python3
"""
Job 85 — Isolate auth SQLite audit-hook tests from the main suite.

Root cause:
  tests/test_auth_p0_isolated.py and tests/test_auth_sessions_isolated.py
  call sys.addaudithook() at import time. Once collected, EVERY other test
  that opens a file-backed SQLite DB fails with:
    - "P0 tests cannot open any file-backed SQLite database"
    - "Session tests must never open workspace SQLite files"

Fix:
  - pytest.ini: ignore both files by default (addopts)
  - CI: main suite ignores them; separate job runs them alone
  - docs note in tests/README_ISOLATED_AUTH.md

Run from repo root:
  python install_job85_isolate_auth_guards.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path.cwd()
PYTEST_INI = ROOT / "pytest.ini"
CI = ROOT / ".github" / "workflows" / "ci.yml"
NOTE = ROOT / "tests" / "README_ISOLATED_AUTH.md"

IGNORE_ARGS = (
    '--ignore=tests/test_auth_p0_isolated.py '
    '--ignore=tests/test_auth_sessions_isolated.py'
)

PYTEST_INI_CONTENT = f"""[pytest]
pythonpath = .
testpaths = tests
# Job 85: auth isolation modules install process-wide sqlite3 audit hooks.
# Run them in a separate process only (see tests/README_ISOLATED_AUTH.md).
addopts =
    {IGNORE_ARGS}
markers =
    integration: tests that require external services such as Ollama
    isolated_auth: process-isolated auth/sqlite guard suites (not in default run)
"""

NOTE_CONTENT = """# Isolated auth tests (Job 85)

These modules register **process-wide** `sys.addaudithook` guards that block
any file-backed SQLite connection. They must **not** be collected with the
main suite.

| File | Guard message |
|------|----------------|
| `test_auth_p0_isolated.py` | P0 tests cannot open any file-backed SQLite database |
| `test_auth_sessions_isolated.py` | Session tests must never open workspace SQLite files |

## Default suite (safe)

```bash
pytest -q -m "not integration"
# pytest.ini already ignores the two files above
```

## Run isolated suites (separate process)

```bash
pytest -q tests/test_auth_p0_isolated.py --tb=short
pytest -q tests/test_auth_sessions_isolated.py --tb=short
```

Do not combine them with the rest of `tests/` in one pytest invocation.
"""


def patch_pytest_ini() -> None:
    PYTEST_INI.write_text(PYTEST_INI_CONTENT, encoding="utf-8")
    print(f"[OK] {PYTEST_INI} — default ignore isolated auth modules")


def patch_ci() -> None:
    if not CI.exists():
        print(f"[WARN] {CI} missing — skip CI patch")
        return
    text = CI.read_text(encoding="utf-8")

    # Main suite: ensure ignores (pytest.ini covers local; CI may override with explicit run)
    old = 'pytest -q --tb=line -m "not integration"'
    new = (
        'pytest -q --tb=line -m "not integration" '
        '--ignore=tests/test_auth_p0_isolated.py '
        '--ignore=tests/test_auth_sessions_isolated.py'
    )
    if "--ignore=tests/test_auth_p0_isolated.py" in text:
        print("[OK] CI main suite already ignores isolated auth")
    elif old in text:
        text = text.replace(old, new, 1)
        print("[OK] CI main suite ignores isolated auth modules")
    else:
        print("[WARN] Could not find main pytest command in CI — edit manually")

    # Add isolated job if missing
    if "test-auth-isolated" in text or "Isolated auth" in text:
        print("[OK] CI isolated auth job already present")
    else:
        job = '''
  test-auth-isolated:
    name: Pytest (isolated auth)
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: requirements.txt
      - name: Install Python dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
      - name: P0 isolated auth (own process)
        env:
          DATABASE_URL: sqlite://
          OLLAMA_HOST: ""
        run: pytest -q tests/test_auth_p0_isolated.py --tb=short
      - name: Session isolated auth (own process)
        env:
          DATABASE_URL: sqlite://
          OLLAMA_HOST: ""
        run: pytest -q tests/test_auth_sessions_isolated.py --tb=short
'''
        text = text.rstrip() + "\n" + job
        print("[OK] CI job test-auth-isolated added")

    CI.write_text(text, encoding="utf-8")


def write_note() -> None:
    NOTE.write_text(NOTE_CONTENT, encoding="utf-8")
    print(f"[OK] {NOTE}")


def main() -> int:
    print("Job 85 — isolate auth SQLite audit-hook tests")
    print(f"ROOT: {ROOT}")
    patch_pytest_ini()
    patch_ci()
    write_note()
    print(
        """
Done. Next:

  pytest -q --tb=line -m "not integration"
  # should NO LONGER show "Session tests must never open workspace SQLite files"

  pytest -q tests/test_auth_p0_isolated.py --tb=short
  pytest -q tests/test_auth_sessions_isolated.py --tb=short

  git add pytest.ini .github/workflows/ci.yml tests/README_ISOLATED_AUTH.md
  git commit -m "Job 85: isolate auth P0/session SQLite audit-hook tests from main suite"
  git push origin development
"""
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
