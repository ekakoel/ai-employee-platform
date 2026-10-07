"""Job 14 — Performance / governance metrics tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.services.seed import seed_catalog

engine = create_engine(
    "sqlite:///./test_governance.db",
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
    co = client.post("/api/v1/companies", json={"name": "Gov Co"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={"name": "Owner", "email": "gov@test.local", "role": "owner"},
    ).json()
    catalog = client.get("/api/v1/agent-catalog").json()
    res = next(i for i in catalog if i["slug"] == "reservation")
    hire = client.post(
        f"/api/v1/companies/{co['id']}/agents/{res['id']}/hire",
        json={"name": "Gov AI"},
        headers={"X-User-ID": owner["id"]},
    )
    assert hire.status_code == 201
    task = client.post(
        f"/api/v1/companies/{co['id']}/tasks",
        headers={"X-User-ID": owner["id"]},
        json={
            "agent_instance_id": hire.json()["id"],
            "title": "Metric task",
            "instruction": "Collect metrics",
            "mode": "consult",
        },
    )
    assert task.status_code == 201
    return co["id"], owner["id"], hire.json()["id"], task.json()["id"]


def test_governance_overview(client):
    company_id, owner_id, agent_id, task_id = setup(client)
    resp = client.get(
        f"/api/v1/companies/{company_id}/governance/overview",
        headers={"X-User-ID": owner_id},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["workforce"]["agents_total"] >= 1
    assert body["tasks"]["total"] >= 1
    assert "by_status" in body["tasks"]
    assert "experiences" in body
    assert "audit" in body


def test_governance_agents(client):
    company_id, owner_id, agent_id, task_id = setup(client)
    resp = client.get(
        f"/api/v1/companies/{company_id}/governance/agents",
        headers={"X-User-ID": owner_id},
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert any(r["agent_instance_id"] == agent_id for r in rows)
    row = next(r for r in rows if r["agent_instance_id"] == agent_id)
    assert row["tasks_total"] >= 1


def test_governance_experiences_and_audit(client):
    company_id, owner_id, agent_id, task_id = setup(client)
    # create + validate experience
    cand = client.post(
        f"/api/v1/companies/{company_id}/tasks/{task_id}/experiences",
        headers={"X-User-ID": owner_id},
        json={"decision": "d", "lesson": "learn", "confidence": 0.5},
    ).json()
    client.post(
        f"/api/v1/companies/{company_id}/experiences/{cand['id']}/validate",
        headers={"X-User-ID": owner_id},
        json={"approve": True, "confidence": 0.9},
    )

    exp = client.get(
        f"/api/v1/companies/{company_id}/governance/experiences",
        headers={"X-User-ID": owner_id},
    )
    assert exp.status_code == 200
    assert exp.json()["validated"] >= 1
    assert exp.json()["avg_confidence_validated"] >= 0.9

    audit = client.get(
        f"/api/v1/companies/{company_id}/governance/audit",
        headers={"X-User-ID": owner_id},
    )
    assert audit.status_code == 200
    assert audit.json()["sample_size"] >= 1
    assert "by_action" in audit.json()


def test_governance_approvals_endpoint(client):
    company_id, owner_id, _, _ = setup(client)
    resp = client.get(
        f"/api/v1/companies/{company_id}/governance/approvals",
        headers={"X-User-ID": owner_id},
    )
    assert resp.status_code == 200
    assert "pending" in resp.json()
    assert "by_status" in resp.json()


def test_workspace_has_governance_nav():
    from fastapi.testclient import TestClient
    from app.main import app

    html = TestClient(app).get("/workspace").content
    assert b"Governance" in html
    assert b'data-view="governance"' in html
