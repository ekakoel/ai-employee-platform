#!/usr/bin/env python3
"""
Job 91 FIX — experience validate body needs approve=True;
delegation create_req(headers=) keyword-only clean.
Also rewrite experience_job10 setup to 5-tuple.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path.cwd()


def fix_job10() -> None:
    p = ROOT / "tests" / "test_experience_job10.py"
    t = p.read_text(encoding="utf-8")

    # setup → 5-tuple
    t = re.sub(
        r"def setup\(client\):[\s\S]*?\n(?=def |\Z)",
        '''def setup(client):
    _cid, _oid, _hdrs, _demo = provision_company(client, hire_agents=False)
    catalog = client.get("/api/v1/agent-catalog").json()
    res = next(i for i in catalog if i["slug"] == "reservation")
    hire = client.post(
        f"/api/v1/companies/{_cid}/agents/{res['id']}/hire",
        json={"name": "J10 AI"},
        headers=_hdrs,
    )
    assert hire.status_code == 201, hire.text
    task = client.post(
        f"/api/v1/companies/{_cid}/tasks",
        headers=_hdrs,
        json={
            "agent_instance_id": hire.json()["id"],
            "title": "Refund case",
            "instruction": "Customer wants refund after late cancel",
        },
    )
    assert task.status_code == 201, task.text
    return _cid, _oid, hire.json()["id"], task.json()["id"], _hdrs


''',
        t,
        count=1,
    )

    t = re.sub(
        r"def validated_experience\([\s\S]*?\n(?=def test_)",
        '''def validated_experience(client, company_id, owner_id, task_id, headers):
    cand = client.post(
        f"/api/v1/companies/{company_id}/tasks/{task_id}/experiences",
        headers=headers,
        json={
            "decision": "Escalate refund",
            "lesson": "Late cancel needs manager",
            "confidence": 0.5,
        },
    )
    assert cand.status_code == 201, cand.text
    body = cand.json()
    val = client.post(
        f"/api/v1/companies/{company_id}/experiences/{body['id']}/validate",
        headers=headers,
        json={"approve": True, "confidence": 0.8, "lesson": "Late cancel needs manager"},
    )
    assert val.status_code == 200, val.text
    return val.json()


''',
        t,
        count=1,
    )

    t = re.sub(
        r"validated_experience\(client, company_id, owner_id, task_id\)",
        "validated_experience(client, company_id, owner_id, task_id, _hdrs)",
        t,
    )
    t = re.sub(
        r"company_id, owner_id, agent_id, (?:_hdrs, )?task_id, _hdrs(?: , _hdrs)? = setup\(client\)",
        "company_id, owner_id, agent_id, task_id, _hdrs = setup(client)",
        t,
    )
    # normalize common unpack forms
    for bad in (
        "company_id, owner_id, agent_id, _hdrs, task_id, _hdrs = setup(client)",
        "company_id, owner_id, agent_id, task_id, _hdrs, _hdrs = setup(client)",
    ):
        t = t.replace(bad, "company_id, owner_id, agent_id, task_id, _hdrs = setup(client)")

    p.write_text(t, encoding="utf-8")
    compile(p.read_text(encoding="utf-8"), str(p), "exec")
    print(f"[OK] {p.name}")


def fix_experience_member() -> None:
    p = ROOT / "tests" / "test_experience.py"
    t = p.read_text(encoding="utf-8")
    # validate body must include approve
    t = t.replace(
        'json={"confidence": 0.9}',
        'json={"approve": True, "confidence": 0.9}',
    )
    t = t.replace(
        'json={"confidence": 0.85}',
        'json={"approve": True, "confidence": 0.85}',
    )
    p.write_text(t, encoding="utf-8")
    print(f"[OK] {p.name} approve field")


def fix_delegation() -> None:
    p = ROOT / "tests" / "test_delegation_execution.py"
    t = p.read_text(encoding="utf-8")

    # Force clean setup + create_req
    t = re.sub(
        r"def setup_two_agents\(client\):[\s\S]*?\n(?=def )",
        '''def setup_two_agents(client):
    _cid, _oid, _hdrs, _demo = provision_company(client, hire_agents=False)
    catalog = client.get("/api/v1/agent-catalog").json()
    res = next(i for i in catalog if i["slug"] == "reservation")
    contract = next(i for i in catalog if i["slug"] == "contract-manager")
    h1 = client.post(
        f"/api/v1/companies/{_cid}/agents/{res['id']}/hire",
        json={"name": "Res AI"},
        headers=_hdrs,
    )
    h2 = client.post(
        f"/api/v1/companies/{_cid}/agents/{contract['id']}/hire",
        json={"name": "Contract AI"},
        headers=_hdrs,
    )
    assert h1.status_code == 201 and h2.status_code == 201, (h1.text, h2.text)
    return _cid, _oid, h1.json()["id"], h2.json()["id"], _hdrs


''',
        t,
        count=1,
    )

    t = re.sub(
        r"def create_req\([\s\S]*?\n(?=def test_)",
        '''def create_req(client, company_id, a1, a2, headers, **extra):
    body = {
        "source_agent_instance_id": a1,
        "target_agent_instance_id": a2,
        "capability": "contract_analysis",
        "title": "Review clause",
        "instruction": "Check termination clause risks.",
        **extra,
    }
    resp = client.post(
        f"/api/v1/companies/{company_id}/delegation-requests",
        headers=headers,
        json=body,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


''',
        t,
        count=1,
    )

    # Normalize all test unpacks and create_req calls
    t = re.sub(
        r"company_id, owner_id, a1, a2(?:, _hdrs)? = setup_two_agents\(client\)",
        "company_id, owner_id, a1, a2, _hdrs = setup_two_agents(client)",
        t,
    )
    # Replace any create_req(...) with clean form — rewrite call by call
    # Pattern variations
    t = re.sub(
        r"create_req\(\s*client,\s*company_id,\s*owner_id,\s*a1,\s*a2\s*\)",
        "create_req(client, company_id, a1, a2, _hdrs)",
        t,
    )
    t = re.sub(
        r"create_req\(\s*client,\s*company_id,\s*owner_id,\s*a1,\s*a2,\s*_hdrs\s*\)",
        "create_req(client, company_id, a1, a2, _hdrs)",
        t,
    )
    t = re.sub(
        r"create_req\(\s*client,\s*company_id,\s*a1,\s*a2,\s*_hdrs\s*\)",
        "create_req(client, company_id, a1, a2, _hdrs)",
        t,
    )
    # With kwargs after agents
    t = re.sub(
        r"create_req\(\s*client,\s*company_id,\s*owner_id,\s*a1,\s*a2,\s*_hdrs,\s*",
        "create_req(client, company_id, a1, a2, _hdrs, ",
        t,
    )
    t = re.sub(
        r"create_req\(\s*client,\s*company_id,\s*owner_id,\s*a1,\s*a2,\s*",
        "create_req(client, company_id, a1, a2, _hdrs, ",
        t,
    )
    # Fix double headers
    t = t.replace(
        "create_req(client, company_id, a1, a2, _hdrs, _hdrs,",
        "create_req(client, company_id, a1, a2, _hdrs,",
    )
    t = t.replace(
        "create_req(client, company_id, a1, a2, _hdrs, headers=",
        "create_req(client, company_id, a1, a2, _hdrs, ",
    )

    p.write_text(t, encoding="utf-8")
    compile(p.read_text(encoding="utf-8"), str(p), "exec")
    print(f"[OK] {p.name}")


def main() -> int:
    print("Job 91 FIX — approve body + clean create_req")
    fix_job10()
    fix_experience_member()
    fix_delegation()
    print(
        """
  pytest -q --tb=line `
    tests/test_experience_job10.py `
    tests/test_experience.py `
    tests/test_delegation_execution.py `
    tests/test_departments_teams.py `
    tests/test_demo_readiness_job53.py

  git add tests/
  git commit -m "Job 91 fix: validate approve field; clean delegation create_req"
  git push origin development
"""
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
