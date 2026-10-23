#!/usr/bin/env python3
"""
Job 86 FIX — remaining setup() unpack sites that still expect old arity.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path.cwd()
TESTS = ROOT / "tests"


def patch(path: Path, replacements: list[tuple[str, str]]) -> None:
    text = path.read_text(encoding="utf-8")
    orig = text
    for old, new in replacements:
        if old not in text:
            print(f"[WARN] not found in {path.name}: {old[:60]!r}")
            continue
        text = text.replace(old, new)
    if text != orig:
        path.write_text(text, encoding="utf-8")
        print(f"[OK] {path.name}")
    else:
        print(f"[OK] {path.name} no change")


def main() -> int:
    print("Job 86 FIX — remaining unpack")
    patch(
        TESTS / "test_experience.py",
        [
            ("    c1, o1, a1, t1 = setup(client)", "    c1, o1, a1, t1, _hdrs = setup(client)"),
        ],
    )
    patch(
        TESTS / "test_governance.py",
        [
            ("    company_id, owner_id, _, _ = setup(client)", "    company_id, owner_id, _, _, _hdrs = setup(client)"),
        ],
    )
    patch(
        TESTS / "test_policy_rules.py",
        [
            (
                "    company_id, owner_id, _, agent_id = setup_company(client)",
                "    company_id, owner_id, _, agent_id, _hdrs = setup_company(client)",
            ),
        ],
    )
    patch(
        TESTS / "test_knowledge_memory.py",
        [
            ("    c1, o1, _ = setup(client)", "    c1, o1, _, _hdrs = setup(client)"),
        ],
    )
    patch(
        TESTS / "test_users_roles_job36.py",
        [
            ("    company_id, owner_id = _owner_company()", "    company_id, owner_id, _hdrs = _owner_company()"),
        ],
    )
    print(
        """
  pytest -q --tb=line -m "not integration" `
    tests/test_experience.py tests/test_governance.py tests/test_policy_rules.py `
    tests/test_knowledge_memory.py tests/test_users_roles_job36.py

  git add tests/
  git commit -m "Job 86 fix: remaining setup unpack arity for _hdrs"
  git push origin development
"""
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
