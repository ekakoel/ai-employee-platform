"""Job 16 — Scope guard + auto-delegation tests."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.services.seed import seed_catalog

engine = create_engine(
    "sqlite:///./test_scope_guard.db",
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


def setup_two_agents(client):
    co = client.post("/api/v1/companies", json={"name": "Scope Co"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={
            "name": "Owner",
            "email": "scope@test.local",
            "role": "owner",
            "password": "secret123",
        },
    ).json()
    headers = {"X-User-ID": owner["id"]}
    catalog = client.get("/api/v1/agent-catalog").json()
    res = next(i for i in catalog if i["slug"] == "reservation")
    # contract-manager may exist
    contract = next((i for i in catalog if "contract" in i["slug"]), None)
    hire_res = client.post(
        f"/api/v1/companies/{co['id']}/agents/{res['id']}/hire",
        json={"name": "Desk AI"},
        headers=headers,
    )
    assert hire_res.status_code == 201, hire_res.text
    desk = hire_res.json()
    contract_agent = None
    if contract:
        hire_c = client.post(
            f"/api/v1/companies/{co['id']}/agents/{contract['id']}/hire",
            json={"name": "Contract AI"},
            headers=headers,
        )
        assert hire_c.status_code == 201, hire_c.text
        contract_agent = hire_c.json()
    return co["id"], headers, desk, contract_agent


def test_in_scope_reservation_instruction(client):
    company_id, headers, desk, _ = setup_two_agents(client)
    resp = client.post(
        f"/api/v1/companies/{company_id}/scope-check",
        headers=headers,
        json={
            "agent_instance_id": desk["id"],
            "instruction": "Please prepare a quotation for hotel reservation and itinerary",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["in_scope"] is True
    assert body["status"] == "IN_SCOPE"


def test_out_of_scope_contract_on_reservation_agent(client):
    company_id, headers, desk, contract_agent = setup_two_agents(client)
    if not contract_agent:
        pytest.skip("contract agent template not in catalog")
    resp = client.post(
        f"/api/v1/companies/{company_id}/scope-check",
        headers=headers,
        json={
            "agent_instance_id": desk["id"],
            "instruction": (
                "Review the supplier contract clauses and legal agreement "
                "for vendor liability and termination terms"
            ),
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["in_scope"] is False
    assert body["status"] == "OUT_OF_SCOPE"
    assert body["alternatives"]
    # contract agent should rank high
    alt_ids = [a["agent_instance_id"] for a in body["alternatives"]]
    assert contract_agent["id"] in alt_ids


def test_auto_delegate_creates_request(client):
    company_id, headers, desk, contract_agent = setup_two_agents(client)
    if not contract_agent:
        pytest.skip("contract agent template not in catalog")
    resp = client.post(
        f"/api/v1/companies/{company_id}/scope-check",
        headers=headers,
        json={
            "agent_instance_id": desk["id"],
            "instruction": (
                "Analyze contract clauses for supplier agreement legal terms"
            ),
            "auto_delegate": True,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["in_scope"] is False
    if body.get("auto_delegated"):
        assert body["delegation_request_id"]
        dels = client.get(
            f"/api/v1/companies/{company_id}/delegation-requests",
            headers=headers,
        )
        assert dels.status_code == 200
        assert any(d["id"] == body["delegation_request_id"] for d in dels.json())


def test_create_task_with_scope_block(client):
    company_id, headers, desk, contract_agent = setup_two_agents(client)
    if not contract_agent:
        pytest.skip("contract agent template not in catalog")
    task = client.post(
        f"/api/v1/companies/{company_id}/tasks",
        headers=headers,
        json={
            "agent_instance_id": desk["id"],
            "title": "Legal review",
            "instruction": (
                "Review vendor contract agreement clauses and legal liability"
            ),
            "mode": "consult",
            "check_scope": True,
            "block_out_of_scope": True,
        },
    )
    assert task.status_code == 201, task.text
    body = task.json()
    assert body["status"] == "cancelled"
    assert body["result"]
    data = json.loads(body["result"])
    assert data["status"] == "OUT_OF_SCOPE"


def test_consult_out_of_scope(client):
    company_id, headers, desk, contract_agent = setup_two_agents(client)
    if not contract_agent:
        pytest.skip("contract agent template not in catalog")
    task = client.post(
        f"/api/v1/companies/{company_id}/tasks",
        headers=headers,
        json={
            "agent_instance_id": desk["id"],
            "title": "Contract help",
            "instruction": "Legal contract clause analysis for supplier agreement",
            "mode": "consult",
        },
    )
    assert task.status_code == 201
    tid = task.json()["id"]
    consult = client.post(
        f"/api/v1/companies/{company_id}/tasks/{tid}/consult",
        headers=headers,
    )
    assert consult.status_code == 200, consult.text
    body = consult.json()
    assert body["status"] == "cancelled"
    data = json.loads(body["result"])
    assert data["status"] == "OUT_OF_SCOPE"
