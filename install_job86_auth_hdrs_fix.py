#!/usr/bin/env python3
"""
Job 86 — Fix NameError _hdrs (setup returns ids but not headers) + token signature.

Root cause:
  Many tests do:
      def setup(client):
          _cid, _oid, _hdrs, _demo = provision_company(client)
          ...
          return company_id, owner_id, agent_id   # _hdrs discarded
      def test_*(client):
          company_id, owner_id, agent_id = setup(client)
          client.post(..., headers=_hdrs)  # NameError

Fix: return _hdrs from setup helpers and unpack in callers.
Also: create_access_token requires session_id + auth_version.

Run from repo root:
  python install_job86_auth_hdrs_fix.py
  pytest -q --tb=line -m "not integration" 2>&1 | Select-Object -Last 30
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path.cwd()
TESTS = ROOT / "tests"


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def write(p: Path, text: str) -> None:
    p.write_text(text, encoding="utf-8")


def fix_automation() -> None:
    p = TESTS / "test_automation.py"
    t = read(p)
    t2 = t.replace(
        '    return co["id"], owner["id"], hire.json()["id"]',
        '    return co["id"], owner["id"], hire.json()["id"], _hdrs',
        1,
    )
    # unpack patterns
    t2 = re.sub(
        r"company_id, owner_id, agent_id = setup\(client\)",
        "company_id, owner_id, agent_id, _hdrs = setup(client)",
        t2,
    )
    if t2 != t:
        write(p, t2)
        print(f"[OK] {p.name}")
    else:
        print(f"[OK] {p.name} (already fixed or pattern changed)")


def fix_consultation() -> None:
    p = TESTS / "test_consultation.py"
    t = read(p)
    t2 = t.replace(
        '    return co["id"], owner["id"], hire.json()["id"]',
        '    return co["id"], owner["id"], hire.json()["id"], _hdrs',
        1,
    )
    t2 = re.sub(
        r"company_id, owner_id, agent_id = setup\(client\)",
        "company_id, owner_id, agent_id, _hdrs = setup(client)",
        t2,
    )
    write(p, t2)
    print(f"[OK] {p.name}")


def fix_experience() -> None:
    p = TESTS / "test_experience.py"
    t = read(p)
    t2 = t.replace(
        '    return co["id"], owner["id"], hire.json()["id"], task.json()["id"]',
        '    return co["id"], owner["id"], hire.json()["id"], task.json()["id"], _hdrs',
        1,
    )
    t2 = re.sub(
        r"company_id, owner_id, agent_id, task_id = setup\(client\)",
        "company_id, owner_id, agent_id, task_id, _hdrs = setup(client)",
        t2,
    )
    write(p, t2)
    print(f"[OK] {p.name}")


def fix_experience_job10() -> None:
    p = TESTS / "test_experience_job10.py"
    if not p.exists():
        print("[SKIP] test_experience_job10.py")
        return
    t = read(p)
    orig = t
    # common returns
    t = t.replace(
        '    return co["id"], owner["id"], hire.json()["id"], task.json()["id"]',
        '    return co["id"], owner["id"], hire.json()["id"], task.json()["id"], _hdrs',
    )
    t = t.replace(
        '    return co["id"], owner["id"], hire.json()["id"]',
        '    return co["id"], owner["id"], hire.json()["id"], _hdrs',
    )
    t = re.sub(
        r"company_id, owner_id, agent_id, task_id = setup\(client\)",
        "company_id, owner_id, agent_id, task_id, _hdrs = setup(client)",
        t,
    )
    t = re.sub(
        r"company_id, owner_id, agent_id = setup\(client\)",
        "company_id, owner_id, agent_id, _hdrs = setup(client)",
        t,
    )
    if t != orig:
        write(p, t)
        print(f"[OK] {p.name}")
    else:
        print(f"[WARN] {p.name} — review manually if still NameError _hdrs")


def fix_governance() -> None:
    p = TESTS / "test_governance.py"
    t = read(p)
    t2 = t.replace(
        '    return co["id"], owner["id"], hire.json()["id"], task.json()["id"]',
        '    return co["id"], owner["id"], hire.json()["id"], task.json()["id"], _hdrs',
        1,
    )
    t2 = re.sub(
        r"company_id, owner_id, agent_id, task_id = setup\(client\)",
        "company_id, owner_id, agent_id, task_id, _hdrs = setup(client)",
        t2,
    )
    write(p, t2)
    print(f"[OK] {p.name}")


def fix_policy_rules() -> None:
    p = TESTS / "test_policy_rules.py"
    t = read(p)
    t2 = t.replace(
        '    return co["id"], owner["id"], member["id"], hire.json()["id"]',
        '    return co["id"], owner["id"], member["id"], hire.json()["id"], _hdrs',
        1,
    )
    t2 = re.sub(
        r"company_id, owner_id, member_id, agent_id = setup_company\(client\)",
        "company_id, owner_id, member_id, agent_id, _hdrs = setup_company(client)",
        t2,
    )
    write(p, t2)
    print(f"[OK] {p.name}")


def fix_knowledge_memory() -> None:
    p = TESTS / "test_knowledge_memory.py"
    t = read(p)
    t2 = t.replace(
        '    return co["id"], owner["id"], hire.json()["id"]',
        '    return co["id"], owner["id"], hire.json()["id"], _hdrs',
        1,
    )
    t2 = re.sub(
        r"company_id, owner_id, agent_id = setup\(client\)",
        "company_id, owner_id, agent_id, _hdrs = setup(client)",
        t2,
    )
    write(p, t2)
    print(f"[OK] {p.name}")


def fix_users_roles() -> None:
    p = TESTS / "test_users_roles_job36.py"
    t = read(p)
    # setup returns only ids
    t2 = t.replace(
        '    return co["id"], owner["id"]',
        '    return co["id"], owner["id"], _hdrs',
        1,
    )
    t2 = re.sub(
        r"company_id, owner_id = setup\(client\)",
        "company_id, owner_id, _hdrs = setup(client)",
        t2,
    )
    # tests may call provision inline
    if "def setup" not in t and "provision_company" in t:
        # file uses inline assign only in one place — ensure tests get headers
        pass
    write(p, t2)
    print(f"[OK] {p.name}")


def fix_production_infra_token() -> None:
    p = TESTS / "test_production_infra.py"
    if not p.exists():
        return
    t = read(p)
    old = 'token = create_access_token(subject="user-1", company_id="co-1")'
    new = (
        'token = create_access_token(\n'
        '        subject="user-1", company_id="co-1",\n'
        '        session_id="sess-test-1", auth_version=1,\n'
        '    )'
    )
    if old in t:
        t = t.replace(old, new, 1)
        write(p, t)
        print(f"[OK] {p.name} create_access_token kwargs")
    else:
        print(f"[OK] {p.name} token call already updated or different")


def fix_helpers_note() -> None:
    """Document that setup must return headers."""
    p = TESTS / "helpers.py"
    t = read(p)
    if "Job 86" in t:
        print("[OK] helpers already noted")
        return
    note = (
        "\n# Job 86: any local setup() that calls provision_company must RETURN headers\n"
        "# e.g. return company_id, owner_id, agent_id, headers\n"
    )
    write(p, t.rstrip() + "\n" + note)
    print("[OK] helpers.py note")


def main() -> int:
    print("Job 86 — fix _hdrs NameError + token signature")
    print(f"ROOT: {ROOT}")
    if not TESTS.is_dir():
        raise SystemExit("tests/ not found — run from repo root")

    fix_automation()
    fix_consultation()
    fix_experience()
    fix_experience_job10()
    fix_governance()
    fix_policy_rules()
    fix_knowledge_memory()
    fix_users_roles()
    fix_production_infra_token()
    fix_helpers_note()

    print(
        """
Done. Verify:

  pytest -q --tb=line -m "not integration" tests/test_automation.py tests/test_consultation.py tests/test_experience.py tests/test_governance.py tests/test_policy_rules.py tests/test_knowledge_memory.py tests/test_users_roles_job36.py

  # broader:
  pytest -q --tb=line -m "not integration" 2>&1 | Select-Object -Last 15

  git add tests/
  git commit -m "Job 86: return auth headers from test setup helpers; fix create_access_token kwargs"
  git push origin development
"""
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
