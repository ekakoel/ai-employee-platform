#!/usr/bin/env python3
"""Job 87 FIX4 — _bearer is (user_id, company_id); drop sessions arg; no duplicate bob insert."""
from __future__ import annotations

import re
import sys
from pathlib import Path

PATH = Path.cwd() / "tests" / "test_chat_workspace.py"


def main() -> int:
    t = PATH.read_text(encoding="utf-8")
    t2 = t.replace('_bearer(sessions, "eve", "two")', '_bearer("eve", "two")')
    t2 = t2.replace("_bearer(sessions, 'eve', 'two')", "_bearer('eve', 'two')")
    t2 = t2.replace('_bearer(sessions, "bob", "one")', '_bearer("bob", "one")')
    t2 = t2.replace("_bearer(sessions, 'bob', 'one')", "_bearer('bob', 'one')")
    t2 = t2.replace('_bearer(sessions, "alice", "one")', '_bearer("alice", "one")')

    # Remove duplicate bob insert in sender attribution test (bob already in fixture)
    t2 = re.sub(
        r'\s*with sessions\(\) as db:\n'
        r'\s*owner = db\.get\(User, "alice"\)\n'
        r'\s*db\.add\(User\(id="bob"[^\n]+\)\n'
        r'\s*db\.commit\(\)\n',
        "\n",
        t2,
        count=1,
    )
    # alternate pattern
    t2 = re.sub(
        r'\s*db\.add\(User\(id="bob", company_id="one"[^\)]*\)\)\n\s*db\.commit\(\)\n',
        "\n",
        t2,
        count=1,
    )

    PATH.write_text(t2, encoding="utf-8")
    compile(PATH.read_text(encoding="utf-8"), str(PATH), "exec")
    print("[OK] chat_workspace bearer calls + no duplicate bob")
    print(
        """
  pytest -q --tb=line tests/test_chat_workspace.py tests/test_agent_directory.py tests/test_scope_guard.py

  git add tests/test_chat_workspace.py
  git commit -m "Job 87 fix4: correct _bearer arity; bob already seeded"
  git push origin development
"""
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
