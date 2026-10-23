#!/usr/bin/env python3
"""
Job 87 FIX3 — User.auth_version must match AuthSession + token ver;
agent_directory remaining unpack.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path.cwd()
CHAT = ROOT / "tests" / "test_chat_workspace.py"
DIR = ROOT / "tests" / "test_agent_directory.py"


def fix_chat_user_auth_version() -> None:
    t = CHAT.read_text(encoding="utf-8")
    # Ensure User rows set auth_version=1
    if "auth_version=1" in t and "User(id=\"alice\"" in t:
        # patch User constructors
        t2 = t
        for uid, email, name, co in [
            ("alice", "alice@test.local", "Alice", "one"),
            ("bob", "bob@test.local", "Bob", "one"),
            ("eve", "eve@test.local", "Eve", "two"),
        ]:
            old = f'User(id="{uid}", company_id="{co}", name="{name}", email="{email}", role_id=role.id)'
            new = (
                f'User(id="{uid}", company_id="{co}", name="{name}", email="{email}", '
                f'role_id=role.id, auth_version=1)'
            )
            if old in t2:
                t2 = t2.replace(old, new)
            elif f'User(id="{uid}"' in t2 and "auth_version" not in t2[t2.find(f'User(id="{uid}"'):t2.find(f'User(id="{uid}"')+120]:
                t2 = re.sub(
                    rf'User\(id="{uid}", company_id="{co}", name="{name}", email="{email}", role_id=role\.id\)',
                    new,
                    t2,
                    count=1,
                )
        CHAT.write_text(t2, encoding="utf-8")
        print("[OK] chat User.auth_version=1")
    else:
        # broader: inject after role_id=role.id for alice/bob/eve
        t2 = re.sub(
            r'(User\(id="(?:alice|bob|eve)"[^)]*role_id=role\.id)(\))',
            r'\1, auth_version=1\2',
            t,
        )
        if t2 != t:
            CHAT.write_text(t2, encoding="utf-8")
            print("[OK] chat auth_version injected")
        else:
            print("[WARN] chat User auth_version — check manually")


def fix_directory_unpack() -> None:
    if not DIR.exists():
        return
    t = DIR.read_text(encoding="utf-8")
    old = "    company_id, owner_id, a1, _ = setup_two_agents(client)"
    new = "    company_id, owner_id, a1, _, _hdrs = setup_two_agents(client)"
    if old in t:
        DIR.write_text(t.replace(old, new), encoding="utf-8")
        print("[OK] agent_directory unpack")
    else:
        # any remaining 4-tuple unpack of setup_two_agents
        t2 = re.sub(
            r"company_id, owner_id, a1, _ = setup_two_agents\(client\)",
            "company_id, owner_id, a1, _, _hdrs = setup_two_agents(client)",
            t,
        )
        t2 = re.sub(
            r"company_id, owner_id, a1, a2 = setup_two_agents\(client\)",
            "company_id, owner_id, a1, a2, _hdrs = setup_two_agents(client)",
            t2,
        )
        if t2 != t:
            DIR.write_text(t2, encoding="utf-8")
            print("[OK] agent_directory unpack (regex)")
        else:
            print("[OK] agent_directory already fine")


def main() -> int:
    print("Job 87 FIX3 — auth_version match + directory unpack")
    fix_chat_user_auth_version()
    fix_directory_unpack()
    print(
        """
  pytest -q --tb=line tests/test_chat_workspace.py tests/test_agent_directory.py tests/test_scope_guard.py

  git add tests/test_chat_workspace.py tests/test_agent_directory.py
  git commit -m "Job 87 fix3: User.auth_version matches session; directory unpack"
  git push origin development
"""
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
