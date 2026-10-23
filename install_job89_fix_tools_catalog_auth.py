#!/usr/bin/env python3
"""Job 89 FIX — /api/v1/tools requires Bearer; use provision headers."""
from __future__ import annotations

from pathlib import Path

PATH = Path.cwd() / "tests" / "test_tools_job19.py"

OLD = '''def test_tool_catalog_endpoint(client):
    resp = client.get("/api/v1/tools")
    assert resp.status_code == 200, resp.text
'''

NEW = '''def test_tool_catalog_endpoint(client):
    # Catalog is authenticated (Bearer required)
    _cid, _oid, headers, _demo = provision_company(client, hire_agents=False)
    resp = client.get("/api/v1/tools", headers=headers)
    assert resp.status_code == 200, resp.text
'''


def main() -> int:
    t = PATH.read_text(encoding="utf-8")
    if "client.get(\"/api/v1/tools\", headers=" in t:
        print("[OK] already auth-aware")
        return 0
    if OLD not in t:
        # softer
        t2 = t.replace(
            '    resp = client.get("/api/v1/tools")\n',
            '    _cid, _oid, headers, _demo = provision_company(client, hire_agents=False)\n'
            '    resp = client.get("/api/v1/tools", headers=headers)\n',
            1,
        )
        if t2 == t:
            raise SystemExit("pattern not found")
        t = t2
    else:
        t = t.replace(OLD, NEW)
    # also hire_agents=False on setup if still default
    t = t.replace(
        "    _cid, _oid, _hdrs, _demo = provision_company(client)\n",
        "    _cid, _oid, _hdrs, _demo = provision_company(client, hire_agents=False)\n",
    )
    PATH.write_text(t, encoding="utf-8")
    compile(PATH.read_text(encoding="utf-8"), str(PATH), "exec")
    print("[OK] test_tools_job19 catalog uses Bearer")
    print(
        """
  pytest -q --tb=line tests/test_tools_job19.py tests/test_marketplace_job30.py tests/test_quotas_job22.py tests/test_result_pins.py tests/test_session_hydrate_job45.py tests/test_production_infra.py

  git add tests/test_tools_job19.py
  git commit -m "Job 89 fix: tool catalog endpoint requires Bearer headers"
  git push origin development
"""
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
