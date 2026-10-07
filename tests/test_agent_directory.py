"""Job 08 — Agent Directory tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.services.directory import build_capabilities
from app.services.seed import seed_catalog

engine = create_engine(
    "sqlite:///./test_agent_directory.db",
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
    co = client.post("/api/v1/companies", json={"name": "Dir Co"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={"name": "Owner", "email": "owner@d.test", "role": "owner"},
    ).json()
    catalog = client.get("/api/v1/agent-catalog").json()
    res = next(i for i in catalog if i["slug"] == "reservation")
    contract = next(i for i in catalog if i["slug"] == "contract-manager")
    h1 = client.post(
        f"/api/v1/companies/{co['id']}/agents/{res['id']}/hire",
        json={"name": "Res AI"},
        headers={"X-User-ID": owner["id"]},
    )
    assert h1.status_code == 201, h1.text
    h2 = client.post(
        f"/api/v1/companies/{co['id']}/agents/{contract['id']}/hire",
        json={"name": "Contract AI"},
        headers={"X-User-ID": owner["id"]},
    )
    assert h2.status_code == 201, h2.text
    return co["id"], owner["id"], h1.json()["id"], h2.json()["id"]


def test_build_capabilities():
    caps = build_capabilities(
        role="Reservation Specialist",
        skills=["availability_check"],
        tools=["search_availability"],
        scope=["reservations"],
    )
    assert "role:reservation_specialist" in caps
    assert "skill:availability_check" in caps
    assert "tool:search_availability" in caps
    assert "scope:reservations" in caps


def test_directory_lists_hired_agents(client):
    company_id, owner_id, a1, a2 = setup_two_agents(client)
    resp = client.get(
        f"/api/v1/companies/{company_id}/directory",
        headers={"X-User-ID": owner_id},
    )
    assert resp.status_code == 200, resp.text
    ids = {e["agent_instance_id"] for e in resp.json()}
    assert a1 in ids and a2 in ids
    for e in resp.json():
        assert "capabilities" in e
        assert len(e["capabilities"]) >= 1


def test_discover_by_skill(client):
    company_id, owner_id, a1, a2 = setup_two_agents(client)
    resp = client.get(
        f"/api/v1/companies/{company_id}/directory/search",
        headers={"X-User-ID": owner_id},
        params={"skill": "contract_analysis"},
    )
    assert resp.status_code == 200
    ids = {e["agent_instance_id"] for e in resp.json()}
    assert a2 in ids
    assert a1 not in ids


def test_validate_target_success(client):
    company_id, owner_id, a1, a2 = setup_two_agents(client)
    resp = client.post(
        f"/api/v1/companies/{company_id}/directory/validate-target",
        headers={"X-User-ID": owner_id},
        json={
            "target_agent_instance_id": a2,
            "required_capability": "contract_analysis",
            "source_agent_instance_id": a1,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["valid"] is True
    assert body["target"]["agent_instance_id"] == a2


def test_validate_target_rejects_self(client):
    company_id, owner_id, a1, _ = setup_two_agents(client)
    resp = client.post(
        f"/api/v1/companies/{company_id}/directory/validate-target",
        headers={"X-User-ID": owner_id},
        json={
            "target_agent_instance_id": a1,
            "source_agent_instance_id": a1,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is False


def test_validate_missing_capability(client):
    company_id, owner_id, a1, a2 = setup_two_agents(client)
    resp = client.post(
        f"/api/v1/companies/{company_id}/directory/validate-target",
        headers={"X-User-ID": owner_id},
        json={
            "target_agent_instance_id": a1,
            "required_capability": "skill:does_not_exist_xyz",
            "source_agent_instance_id": a2,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is False


def test_create_delegation_request(client):
    company_id, owner_id, a1, a2 = setup_two_agents(client)
    resp = client.post(
        f"/api/v1/companies/{company_id}/delegation-requests",
        headers={"X-User-ID": owner_id},
        json={
            "source_agent_instance_id": a1,
            "target_agent_instance_id": a2,
            "capability": "contract_analysis",
            "title": "Check supplier contract",
            "instruction": "Review the supplier terms for clause risks.",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["source_agent_instance_id"] == a1
    assert body["target_agent_instance_id"] == a2

    listed = client.get(
        f"/api/v1/companies/{company_id}/delegation-requests",
        headers={"X-User-ID": owner_id},
    )
    assert listed.status_code == 200
    assert any(r["id"] == body["id"] for r in listed.json())


def test_delegation_rejects_invalid_target(client):
    company_id, owner_id, a1, a2 = setup_two_agents(client)
    resp = client.post(
        f"/api/v1/companies/{company_id}/delegation-requests",
        headers={"X-User-ID": owner_id},
        json={
            "source_agent_instance_id": a1,
            "target_agent_instance_id": a2,
            "capability": "nonexistent_capability_zzz",
            "title": "Bad",
            "instruction": "Nope",
        },
    )
    assert resp.status_code == 400
