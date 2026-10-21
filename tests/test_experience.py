"""Phase 7 — Experience learning tests."""

import pytest
from fastapi.testclient import TestClient

from tests.helpers import owner_setup, provision_company, bootstrap_demo, login_headers
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.services.seed import seed_catalog

engine = create_engine(
    "sqlite:///./test_experience.db",
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


def setup(client):
    # auth-hardened: demo bootstrap instead of public company create
    _cid, _oid, _hdrs, _demo = provision_company(client)
    co = {"id": _cid}
    owner = {"id": _oid, "email": _demo.get("owner_email")}
    catalog = client.get("/api/v1/agent-catalog").json()
    res = next(i for i in catalog if i["slug"] == "reservation")
    hire = client.post(
        f"/api/v1/companies/{co['id']}/agents/{res['id']}/hire",
        json={"name": "Exp AI"},
        headers=_hdrs,
    )
    assert hire.status_code == 201
    task = client.post(
        f"/api/v1/companies/{co['id']}/tasks",
        headers=_hdrs,
        json={
            "agent_instance_id": hire.json()["id"],
            "title": "Refund request",
            "instruction": "Customer asks for refund on cancelled booking",
        },
    )
    assert task.status_code == 201, task.text
    return co["id"], owner["id"], hire.json()["id"], task.json()["id"], _hdrs


def test_create_candidate_from_task(client):
    company_id, owner_id, agent_id, task_id, _hdrs = setup(client)
    resp = client.post(
        f"/api/v1/companies/{company_id}/tasks/{task_id}/experiences",
        headers=_hdrs,
        json={
            "decision": "Escalate to manager for refund",
            "action": "Created approval request",
            "lesson": "Refunds above policy always need approval",
            "confidence": 0.5,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["validation_status"] == "candidate"
    assert body["source_task_id"] == task_id
    assert body["agent_instance_id"] == agent_id
    assert "Refund" in body["situation"] or "refund" in body["problem"].lower()


def test_validate_and_search(client):
    company_id, owner_id, agent_id, task_id, _hdrs = setup(client)
    cand = client.post(
        f"/api/v1/companies/{company_id}/tasks/{task_id}/experiences",
        headers=_hdrs,
        json={
            "decision": "Require manager approval for refund",
            "lesson": "Never auto-refund without policy check",
            "confidence": 0.6,
        },
    ).json()

    # not searchable until validated
    search0 = client.post(
        f"/api/v1/companies/{company_id}/experiences/search",
        headers=_hdrs,
        json={"query": "refund approval", "limit": 5},
    )
    assert search0.status_code == 200
    assert all(h["id"] != cand["id"] for h in search0.json())

    validated = client.post(
        f"/api/v1/companies/{company_id}/experiences/{cand['id']}/validate",
        headers=_hdrs,
        json={
            "approve": True,
            "lesson": "Validated lesson: refunds need manager approval",
            "confidence": 0.85,
        },
    )
    assert validated.status_code == 200, validated.text
    assert validated.json()["validation_status"] == "validated"
    assert validated.json()["confidence"] == 0.85

    search1 = client.post(
        f"/api/v1/companies/{company_id}/experiences/search",
        headers=_hdrs,
        json={"query": "refund manager approval", "limit": 5},
    )
    assert search1.status_code == 200
    hits = search1.json()
    assert any(h["id"] == cand["id"] for h in hits)


def test_reject_experience(client):
    company_id, owner_id, agent_id, task_id, _hdrs = setup(client)
    cand = client.post(
        f"/api/v1/companies/{company_id}/tasks/{task_id}/experiences",
        headers=_hdrs,
        json={"decision": "Bad lesson", "lesson": "Ignore policy"},
    ).json()
    rejected = client.post(
        f"/api/v1/companies/{company_id}/experiences/{cand['id']}/validate",
        headers=_hdrs,
        json={"approve": False, "human_correction": "Unsafe lesson rejected"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["validation_status"] == "rejected"


def test_tenant_isolation(client):
    c1, o1, a1, t1, _hdrs = setup(client)
    cand = client.post(
        f"/api/v1/companies/{c1}/tasks/{t1}/experiences",
        headers={"X-User-ID": o1},
        json={"decision": "SecretExpToken999", "lesson": "SecretExpToken999"},
    ).json()
    client.post(
        f"/api/v1/companies/{c1}/experiences/{cand['id']}/validate",
        headers={"X-User-ID": o1},
        json={"approve": True, "confidence": 0.9},
    )

    # auth-hardened: demo bootstrap instead of public company create
    _cid, _oid, _hdrs, _demo = provision_company(client)
    co2 = {"id": _cid}
    o2 = client.post(
        f"/api/v1/companies/{co2['id']}/users",
        json={"name": "O2", "email": "o2@e.test", "role": "owner"},
    ).json()
    search = client.post(
        f"/api/v1/companies/{co2['id']}/experiences/search",
        headers={"X-User-ID": o2["id"]},
        json={"query": "SecretExpToken999", "limit": 5},
    )
    assert search.status_code == 200
    assert search.json() == []


def test_member_cannot_validate(client):
    company_id, owner_id, agent_id, task_id, _hdrs = setup(client)
    member = client.post(
        f"/api/v1/companies/{company_id}/users",
        headers=_hdrs,
        json={"name": "Member", "email": "m@e.test", "role": "member"},
    ).json()
    cand = client.post(
        f"/api/v1/companies/{company_id}/tasks/{task_id}/experiences",
        headers=_hdrs,
        json={"decision": "x", "lesson": "y"},
    ).json()
    resp = client.post(
        f"/api/v1/companies/{company_id}/experiences/{cand['id']}/validate",
        headers={"X-User-ID": member["id"]},
        json={"approve": True},
    )
    assert resp.status_code == 403
