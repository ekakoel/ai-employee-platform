"""Job 10 — Experience system completion (feedback, confidence, reuse)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.services.seed import seed_catalog

engine = create_engine(
    "sqlite:///./test_experience_job10.db",
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
    co = client.post("/api/v1/companies", json={"name": "Job10 Co"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={"name": "Owner", "email": "o@j10.test", "role": "owner"},
    ).json()
    catalog = client.get("/api/v1/agent-catalog").json()
    res = next(i for i in catalog if i["slug"] == "reservation")
    hire = client.post(
        f"/api/v1/companies/{co['id']}/agents/{res['id']}/hire",
        json={"name": "J10 AI"},
        headers={"X-User-ID": owner["id"]},
    )
    task = client.post(
        f"/api/v1/companies/{co['id']}/tasks",
        headers={"X-User-ID": owner["id"]},
        json={
            "agent_instance_id": hire.json()["id"],
            "title": "Refund case",
            "instruction": "Customer wants refund after late cancel",
        },
    )
    return co["id"], owner["id"], hire.json()["id"], task.json()["id"]


def validated_experience(client, company_id, owner_id, task_id):
    cand = client.post(
        f"/api/v1/companies/{company_id}/tasks/{task_id}/experiences",
        headers={"X-User-ID": owner_id},
        json={
            "decision": "Escalate refund",
            "lesson": "Late cancel needs manager",
            "confidence": 0.5,
        },
    ).json()
    val = client.post(
        f"/api/v1/companies/{company_id}/experiences/{cand['id']}/validate",
        headers={"X-User-ID": owner_id},
        json={"approve": True, "confidence": 0.8, "lesson": "Late cancel needs manager"},
    )
    assert val.status_code == 200
    return val.json()


def test_job10_matrix_candidate_validate_retrieve_confidence_feedback(client):
    company_id, owner_id, agent_id, task_id = setup(client)
    exp = validated_experience(client, company_id, owner_id, task_id)
    assert exp["validation_status"] == "validated"
    assert exp["confidence"] == 0.8

    # retrieval
    hits = client.post(
        f"/api/v1/companies/{company_id}/experiences/search",
        headers={"X-User-ID": owner_id},
        json={"query": "refund late cancel manager", "limit": 5},
    )
    assert hits.status_code == 200
    assert any(h["id"] == exp["id"] for h in hits.json())

    # helpful feedback raises confidence + success_count
    fb = client.post(
        f"/api/v1/companies/{company_id}/experiences/{exp['id']}/feedback",
        headers={"X-User-ID": owner_id},
        json={
            "helpful": True,
            "human_correction": "Also document policy id REF-1",
            "confidence_delta": 0.05,
        },
    )
    assert fb.status_code == 200, fb.text
    assert fb.json()["success_count"] >= 1
    assert fb.json()["confidence"] >= 0.85
    assert "REF-1" in fb.json()["human_correction"]


def test_unhelpful_feedback_lowers_confidence(client):
    company_id, owner_id, agent_id, task_id = setup(client)
    exp = validated_experience(client, company_id, owner_id, task_id)
    before = exp["confidence"]
    fb = client.post(
        f"/api/v1/companies/{company_id}/experiences/{exp['id']}/feedback",
        headers={"X-User-ID": owner_id},
        json={"helpful": False, "human_correction": "Lesson was incomplete"},
    )
    assert fb.status_code == 200
    assert fb.json()["confidence"] < before


def test_feedback_only_on_validated(client):
    company_id, owner_id, agent_id, task_id = setup(client)
    cand = client.post(
        f"/api/v1/companies/{company_id}/tasks/{task_id}/experiences",
        headers={"X-User-ID": owner_id},
        json={"decision": "x", "lesson": "y"},
    ).json()
    fb = client.post(
        f"/api/v1/companies/{company_id}/experiences/{cand['id']}/feedback",
        headers={"X-User-ID": owner_id},
        json={"helpful": True},
    )
    assert fb.status_code == 409


def test_reuse_bumps_success_count(client):
    company_id, owner_id, agent_id, task_id = setup(client)
    exp = validated_experience(client, company_id, owner_id, task_id)
    r1 = client.post(
        f"/api/v1/companies/{company_id}/experiences/{exp['id']}/reuse",
        headers={"X-User-ID": owner_id},
    )
    assert r1.status_code == 200
    assert r1.json()["success_count"] >= 1
    conf1 = r1.json()["confidence"]
    r2 = client.post(
        f"/api/v1/companies/{company_id}/experiences/{exp['id']}/reuse",
        headers={"X-User-ID": owner_id},
    )
    assert r2.json()["success_count"] >= 2
    assert r2.json()["confidence"] >= conf1


def test_archive_hides_from_search(client):
    company_id, owner_id, agent_id, task_id = setup(client)
    exp = validated_experience(client, company_id, owner_id, task_id)
    arch = client.post(
        f"/api/v1/companies/{company_id}/experiences/{exp['id']}/archive",
        headers={"X-User-ID": owner_id},
    )
    assert arch.status_code == 200
    assert arch.json()["validation_status"] == "archived"
    assert arch.json()["is_active"] is False

    hits = client.post(
        f"/api/v1/companies/{company_id}/experiences/search",
        headers={"X-User-ID": owner_id},
        json={"query": "refund late cancel manager", "limit": 5},
    )
    assert all(h["id"] != exp["id"] for h in hits.json())


def test_get_experience(client):
    company_id, owner_id, agent_id, task_id = setup(client)
    exp = validated_experience(client, company_id, owner_id, task_id)
    got = client.get(
        f"/api/v1/companies/{company_id}/experiences/{exp['id']}",
        headers={"X-User-ID": owner_id},
    )
    assert got.status_code == 200
    assert got.json()["id"] == exp["id"]


def test_manual_candidate_create_fixed(client):
    """Regression: POST /experiences must not crash (signature fix)."""
    company_id, owner_id, agent_id, task_id = setup(client)
    resp = client.post(
        f"/api/v1/companies/{company_id}/experiences",
        headers={"X-User-ID": owner_id},
        json={
            "agent_instance_id": agent_id,
            "problem": "Manual candidate problem",
            "decision": "Do X",
            "lesson": "Learn Y",
            "confidence": 0.4,
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["validation_status"] == "candidate"
