"""Job 17 — Policy simulation + approval routing tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.services.seed import seed_catalog

engine = create_engine(
    "sqlite:///./test_policy_simulate.db",
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

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


def setup(client):
    co = client.post("/api/v1/companies", json={"name": "Sim Co"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={
            "name": "Owner",
            "email": "sim@test.local",
            "role": "owner",
            "password": "secret123",
        },
    ).json()
    headers = {"X-User-ID": owner["id"]}
    catalog = client.get("/api/v1/agent-catalog").json()
    res = next(i for i in catalog if i["slug"] == "reservation")
    hire = client.post(
        f"/api/v1/companies/{co['id']}/agents/{res['id']}/hire",
        json={"name": "Desk AI"},
        headers=headers,
    )
    assert hire.status_code == 201
    return co["id"], headers, hire.json()["id"], owner["id"]


def test_simulate_default_deny(client):
    company_id, headers, agent_id, _ = setup(client)
    resp = client.post(
        f"/api/v1/companies/{company_id}/policies/simulate",
        headers=headers,
        json={
            "agent_instance_id": agent_id,
            "tool_name": "search_contract",
            "arguments": {"query": "x"},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["simulation"] is True
    assert body["effect"] == "deny"
    assert body["allowed"] is False
    assert body["denied"] is True
    assert "considered_policies" in body


def test_simulate_deny(client):
    company_id, headers, agent_id, _ = setup(client)
    pol = client.post(
        f"/api/v1/companies/{company_id}/policies",
        headers=headers,
        json={
            "name": "Deny search",
            "description": "Block search_contract",
            "configuration": {
                "tool": "search_contract",
                "effect": "deny",
                "priority": 10,
            },
        },
    )
    assert pol.status_code == 201, pol.text
    resp = client.post(
        f"/api/v1/companies/{company_id}/policies/simulate",
        headers=headers,
        json={
            "agent_instance_id": agent_id,
            "tool_name": "search_contract",
            "arguments": {},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["effect"] == "deny"
    assert body["denied"] is True
    assert body["policy_id"] == pol.json()["id"]


def test_simulate_require_approval_with_route(client):
    company_id, headers, agent_id, owner_id = setup(client)
    pol = client.post(
        f"/api/v1/companies/{company_id}/policies",
        headers=headers,
        json={
            "name": "Approve large refund",
            "configuration": {
                "tool": "issue_refund",
                "effect": "require_approval",
                "approval_level": "owner",
                "priority": 5,
                "conditions": {"amount_gt": 1000},
            },
        },
    )
    assert pol.status_code == 201, pol.text

    # An unmatched conditional rule does not authorize the action.
    low = client.post(
        f"/api/v1/companies/{company_id}/policies/simulate",
        headers=headers,
        json={
            "agent_instance_id": agent_id,
            "tool_name": "issue_refund",
            "arguments": {"amount": 50},
        },
    )
    assert low.status_code == 200
    assert low.json()["effect"] == "deny"

    high = client.post(
        f"/api/v1/companies/{company_id}/policies/simulate",
        headers=headers,
        json={
            "agent_instance_id": agent_id,
            "tool_name": "issue_refund",
            "arguments": {"amount": 5000},
        },
    )
    assert high.status_code == 200
    body = high.json()
    assert body["effect"] == "require_approval"
    assert body["requires_approval"] is True
    assert body["approval_level"] == "owner"
    assert body["route_to_role"] == "owner"
    assert body["route_to_user_id"] == owner_id
    assert body["route_explanation"]


def test_simulate_department_condition(client):
    company_id, headers, agent_id, _ = setup(client)
    client.post(
        f"/api/v1/companies/{company_id}/policies",
        headers=headers,
        json={
            "name": "Sales only tool",
            "configuration": {
                "tool": "send_quote",
                "effect": "allow",
                "priority": 1,
                "conditions": {"department": "sales"},
            },
        },
    )
    miss = client.post(
        f"/api/v1/companies/{company_id}/policies/simulate",
        headers=headers,
        json={
            "agent_instance_id": agent_id,
            "tool_name": "send_quote",
            "arguments": {},
            "context": {"department": "ops"},
        },
    )
    assert miss.json()["effect"] == "deny"  # Unmatched actions fail closed.

    hit = client.post(
        f"/api/v1/companies/{company_id}/policies/simulate",
        headers=headers,
        json={
            "agent_instance_id": agent_id,
            "tool_name": "send_quote",
            "arguments": {},
            "context": {"department": "sales"},
        },
    )
    assert hit.json()["effect"] == "allow"
    assert hit.json()["policy_name"] == "Sales only tool"
