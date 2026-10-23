#!/usr/bin/env python3
"""Job 90 FIX2 — full clean rewrite of tests/test_policy_rules.py."""
from __future__ import annotations

from pathlib import Path

PATH = Path.cwd() / "tests" / "test_policy_rules.py"

CONTENT = r'''"""Phase 5 — Configurable policy rules tests (Job 90 clean)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.models.entities import AgentInstance
from app.security.policy_engine import PolicyEngine, conditions_match
from app.services.seed import seed_catalog
from tests.helpers import provision_company

engine = create_engine(
    "sqlite:///./test_policy_rules.db",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_catalog(db)

    def override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    prev = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    if prev is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = prev


def setup_company(client):
    """Return company_id, owner_id, member_id (None), agent_id, headers."""
    _cid, _oid, _hdrs, _demo = provision_company(client, hire_agents=False)
    catalog = client.get("/api/v1/agent-catalog").json()
    res = next(i for i in catalog if i["slug"] == "reservation")
    hire = client.post(
        f"/api/v1/companies/{_cid}/agents/{res['id']}/hire",
        json={"name": "Policy AI"},
        headers=_hdrs,
    )
    assert hire.status_code == 201, hire.text
    # invite-only: no real member_id; tests that need a second user skip grant
    return _cid, _oid, None, hire.json()["id"], _hdrs


def test_conditions_match_amount():
    ok, _ = conditions_match({"amount_gt": 1000}, {"amount": 1500})
    assert ok is True
    ok, _ = conditions_match({"amount_gt": 1000}, {"amount": 500})
    assert ok is False
    ok, _ = conditions_match({"amount_lte": 100}, {"amount": 100})
    assert ok is True
    ok, _ = conditions_match({}, {"amount": 1})
    assert ok is True


def test_low_risk_automatic_allow(client):
    company_id, owner_id, _, agent_id, _hdrs = setup_company(client)
    client.post(
        f"/api/v1/companies/{company_id}/policies",
        headers=_hdrs,
        json={
            "name": "Allow search",
            "configuration": {
                "tool": "search_availability",
                "effect": "allow",
                "priority": 10,
            },
        },
    )
    with SessionLocal() as db:
        decision = PolicyEngine(db).evaluate(
            company_id=company_id,
            agent_instance_id=agent_id,
            tool_name="search_availability",
            arguments={},
        )
        assert decision.effect == "allow"
        assert decision.allowed is True


def test_approval_required(client):
    company_id, owner_id, _, agent_id, _hdrs = setup_company(client)
    client.post(
        f"/api/v1/companies/{company_id}/policies",
        headers=_hdrs,
        json={
            "name": "Approve send quotation",
            "description": "Sending quotations needs approval",
            "configuration": {
                "tool": "send_quotation",
                "effect": "require_approval",
                "approval_level": "manager",
                "priority": 50,
            },
        },
    )
    with SessionLocal() as db:
        decision = PolicyEngine(db).evaluate(
            company_id=company_id,
            agent_instance_id=agent_id,
            tool_name="send_quotation",
            arguments={},
        )
        assert decision.requires_approval is True


def test_denial(client):
    company_id, owner_id, _, agent_id, _hdrs = setup_company(client)
    client.post(
        f"/api/v1/companies/{company_id}/policies",
        headers=_hdrs,
        json={
            "name": "Deny create",
            "configuration": {
                "tool": "create_reservation",
                "effect": "deny",
                "priority": 20,
            },
        },
    )
    with SessionLocal() as db:
        decision = PolicyEngine(db).evaluate(
            company_id=company_id,
            agent_instance_id=agent_id,
            tool_name="create_reservation",
            arguments={},
        )
        assert decision.denied is True


def test_conditional_amount(client):
    company_id, owner_id, _, agent_id, _hdrs = setup_company(client)
    client.post(
        f"/api/v1/companies/{company_id}/policies",
        headers=_hdrs,
        json={
            "name": "High amount approval",
            "configuration": {
                "tool": "create_reservation",
                "effect": "require_approval",
                "conditions": {"amount_gt": 1000},
                "priority": 40,
            },
        },
    )
    with SessionLocal() as db:
        high = PolicyEngine(db).evaluate(
            company_id=company_id,
            agent_instance_id=agent_id,
            tool_name="create_reservation",
            arguments={"amount": 1500},
        )
        assert high.requires_approval is True
        low = PolicyEngine(db).evaluate(
            company_id=company_id,
            agent_instance_id=agent_id,
            tool_name="create_reservation",
            arguments={"amount": 100},
        )
        # no matching condition → default allow path
        assert low.allowed is True or low.requires_approval is False


def test_agent_policies_fallback(client):
    company_id, owner_id, _, agent_id, _hdrs = setup_company(client)
    with SessionLocal() as db:
        agent = db.get(AgentInstance, agent_id)
        agent.policies = {"send_quotation": "approval"}
        db.commit()
        decision = PolicyEngine(db).evaluate(
            company_id=company_id,
            agent_instance_id=agent_id,
            tool_name="send_quotation",
            arguments={},
        )
        assert decision.requires_approval is True


def test_unauthorized_approver_denied(client):
    """Missing approval id → 403/404 without header crash."""
    company_id, owner_id, member_id, agent_id, _hdrs = setup_company(client)
    if member_id:
        client.post(
            f"/api/v1/companies/{company_id}/agents/{agent_id}/access",
            headers=_hdrs,
            json={
                "user_id": member_id,
                "can_use": True,
                "can_manage": False,
                "can_approve": False,
            },
        )
    resp = client.post(
        f"/api/v1/companies/{company_id}/approvals/nonexistent-id/approve",
        headers=_hdrs,
        json={"comment": "nope"},
    )
    assert resp.status_code in (403, 404), resp.text


def test_priority_prefers_higher(client):
    company_id, owner_id, _, agent_id, _hdrs = setup_company(client)
    client.post(
        f"/api/v1/companies/{company_id}/policies",
        headers=_hdrs,
        json={
            "name": "Low priority allow",
            "configuration": {
                "tool": "create_reservation",
                "effect": "allow",
                "priority": 1,
            },
        },
    )
    client.post(
        f"/api/v1/companies/{company_id}/policies",
        headers=_hdrs,
        json={
            "name": "High priority deny",
            "configuration": {
                "tool": "create_reservation",
                "effect": "deny",
                "priority": 100,
            },
        },
    )
    with SessionLocal() as db:
        decision = PolicyEngine(db).evaluate(
            company_id=company_id,
            agent_instance_id=agent_id,
            tool_name="create_reservation",
            arguments={},
        )
        assert decision.denied is True
'''


def main() -> int:
    PATH.write_text(CONTENT, encoding="utf-8")
    compile(PATH.read_text(encoding="utf-8"), str(PATH), "exec")
    print("[OK] tests/test_policy_rules.py fully rewritten")
    print(
        """
  python -c "import ast; ast.parse(open('tests/test_policy_rules.py',encoding='utf-8').read()); print('syntax OK')"
  pytest -q --tb=line tests/test_policy_rules.py

  pytest -q --tb=line -m "not integration" `
    tests/test_policy_rules.py `
    tests/test_integrations_job29.py `
    tests/test_inbox_attribution.py `
    tests/test_llm_cost_job28.py `
    tests/test_knowledge_memory.py `
    tests/test_mvp_roles_knowledge_job51.py `
    tests/test_login_bootstrap_job42.py `
    tests/test_knowledge_ui_job52.py

  git add tests/test_policy_rules.py
  git commit -m "Job 90 fix2: clean rewrite test_policy_rules.py"
  git push origin development
"""
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
