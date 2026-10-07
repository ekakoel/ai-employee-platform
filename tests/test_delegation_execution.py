"""Job 09 — Inter-agent delegation execution tests."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.models.entities import DelegationRequest, Task
from app.services.seed import seed_catalog

engine = create_engine(
    "sqlite:///./test_delegation_execution.db",
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


def setup_two_agents(client):
    co = client.post("/api/v1/companies", json={"name": "Del Co"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={"name": "Owner", "email": "owner@del.test", "role": "owner"},
    ).json()
    catalog = client.get("/api/v1/agent-catalog").json()
    res = next(i for i in catalog if i["slug"] == "reservation")
    contract = next(i for i in catalog if i["slug"] == "contract-manager")
    h1 = client.post(
        f"/api/v1/companies/{co['id']}/agents/{res['id']}/hire",
        json={"name": "Res AI"},
        headers={"X-User-ID": owner["id"]},
    )
    h2 = client.post(
        f"/api/v1/companies/{co['id']}/agents/{contract['id']}/hire",
        json={"name": "Contract AI"},
        headers={"X-User-ID": owner["id"]},
    )
    assert h1.status_code == 201 and h2.status_code == 201
    return co["id"], owner["id"], h1.json()["id"], h2.json()["id"]


def create_req(client, company_id, owner_id, a1, a2, **extra):
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
        headers={"X-User-ID": owner_id},
        json=body,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_execute_creates_child_task_and_completes(client):
    company_id, owner_id, a1, a2 = setup_two_agents(client)
    req = create_req(client, company_id, owner_id, a1, a2)

    run = client.post(
        f"/api/v1/companies/{company_id}/delegation-requests/{req['id']}/execute",
        headers={"X-User-ID": owner_id},
        json={"mode": "consult"},
    )
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["status"] == "completed"
    assert body["child_task_id"]
    assert body["result"]
    payload = json.loads(body["result"])
    assert payload["child_task_id"] == body["child_task_id"]
    assert payload["capability"] == "contract_analysis"

    with SessionLocal() as db:
        child = db.get(Task, body["child_task_id"])
        assert child is not None
        assert child.agent_instance_id == a2
        assert child.status == "completed"
        assert child.mode == "consult"


def test_accept_and_reject(client):
    company_id, owner_id, a1, a2 = setup_two_agents(client)
    req = create_req(client, company_id, owner_id, a1, a2)
    acc = client.post(
        f"/api/v1/companies/{company_id}/delegation-requests/{req['id']}/accept",
        headers={"X-User-ID": owner_id},
    )
    assert acc.status_code == 200
    assert acc.json()["status"] == "accepted"

    req2 = create_req(client, company_id, owner_id, a1, a2, title="Other")
    rej = client.post(
        f"/api/v1/companies/{company_id}/delegation-requests/{req2['id']}/reject",
        headers={"X-User-ID": owner_id},
        params={"reason": "Out of scope"},
    )
    assert rej.status_code == 200
    assert rej.json()["status"] == "rejected"


def test_cancel(client):
    company_id, owner_id, a1, a2 = setup_two_agents(client)
    req = create_req(client, company_id, owner_id, a1, a2)
    can = client.post(
        f"/api/v1/companies/{company_id}/delegation-requests/{req['id']}/cancel",
        headers={"X-User-ID": owner_id},
    )
    assert can.status_code == 200
    assert can.json()["status"] == "cancelled"


def test_timeout_marks_failed(client):
    company_id, owner_id, a1, a2 = setup_two_agents(client)
    req = create_req(
        client, company_id, owner_id, a1, a2, timeout_seconds=1, title="Timeout me"
    )
    with SessionLocal() as db:
        row = db.get(DelegationRequest, req["id"])
        row.created_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        db.commit()

    got = client.get(
        f"/api/v1/companies/{company_id}/delegation-requests/{req['id']}",
        headers={"X-User-ID": owner_id},
    )
    assert got.status_code == 200
    assert got.json()["status"] == "failed"
    assert "timed out" in (got.json().get("error_message") or "").lower()


def test_execute_after_timeout_fails(client):
    company_id, owner_id, a1, a2 = setup_two_agents(client)
    req = create_req(
        client, company_id, owner_id, a1, a2, timeout_seconds=1, title="Late"
    )
    with SessionLocal() as db:
        row = db.get(DelegationRequest, req["id"])
        row.created_at = datetime.now(timezone.utc) - timedelta(seconds=30)
        db.commit()

    run = client.post(
        f"/api/v1/companies/{company_id}/delegation-requests/{req['id']}/execute",
        headers={"X-User-ID": owner_id},
        json={"mode": "consult"},
    )
    assert run.status_code == 409


def test_cannot_execute_twice(client):
    company_id, owner_id, a1, a2 = setup_two_agents(client)
    req = create_req(client, company_id, owner_id, a1, a2)
    first = client.post(
        f"/api/v1/companies/{company_id}/delegation-requests/{req['id']}/execute",
        headers={"X-User-ID": owner_id},
        json={"mode": "consult"},
    )
    assert first.status_code == 200
    second = client.post(
        f"/api/v1/companies/{company_id}/delegation-requests/{req['id']}/execute",
        headers={"X-User-ID": owner_id},
        json={"mode": "consult"},
    )
    assert second.status_code == 409


def test_execute_mode_leaves_child_pending(client):
    company_id, owner_id, a1, a2 = setup_two_agents(client)
    req = create_req(client, company_id, owner_id, a1, a2, title="Exec mode")
    run = client.post(
        f"/api/v1/companies/{company_id}/delegation-requests/{req['id']}/execute",
        headers={"X-User-ID": owner_id},
        json={"mode": "execute"},
    )
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["status"] == "accepted"
    assert body["child_task_id"]
    with SessionLocal() as db:
        child = db.get(Task, body["child_task_id"])
        assert child.status == "pending"
        assert child.mode == "execute"
