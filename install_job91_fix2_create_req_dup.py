#!/usr/bin/env python3
"""Job 91 FIX2 — remove duplicate _hdrs positional arg in create_req calls."""
from pathlib import Path

p = Path.cwd() / "tests" / "test_delegation_execution.py"
t = p.read_text(encoding="utf-8")
t2 = t.replace(
    "create_req(client, company_id, a1, a2, _hdrs, _hdrs)",
    "create_req(client, company_id, a1, a2, _hdrs)",
)
# also any trailing double
t2 = t2.replace(
    "create_req(client, company_id, a1, a2, _hdrs, _hdrs,",
    "create_req(client, company_id, a1, a2, _hdrs,",
)
p.write_text(t2, encoding="utf-8")
n = t.count("create_req(client, company_id, a1, a2, _hdrs, _hdrs)")
compile(p.read_text(encoding="utf-8"), str(p), "exec")
print(f"[OK] removed {n} duplicate _hdrs args")
print(
    """
  pytest -q --tb=line tests/test_delegation_execution.py tests/test_experience_job10.py tests/test_experience.py

  git add tests/test_delegation_execution.py
  git commit -m "Job 91 fix2: remove duplicate _hdrs in create_req calls"
  git push origin development
"""
)
