"""Phase 3 — Human AI Access tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.services.seed import seed_catalog

engine = create_engine(
    "sqlite:///./test_agent_access.db",
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
    co = client.post("/api/v1/companies", json={"name": "Access Co"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={"name": "Owner", "email": "owner@a.test", "role": "owner"},
    ).json()
    member = client.post(
        f"/api/v1/companies/{co['id']}/users",
        headers={"X-User-ID": owner["id"]},
        json={"name": "Member", "email": "member@a.test", "role": "member"},
    ).json()
    catalog = client.get("/api/v1/agent-catalog").json()
    res = next(i for i in catalog if i["slug"] == "reservation")
    hire = client.post(
        f"/api/v1/companies/{co['id']}/agents/{res['id']}/hire",
        json={"name": "Desk AI"},
        headers={"X-User-ID": owner["id"]},
    )
    assert hire.status_code == 201, hire.text
    return co["id"], owner["id"], member["id"], hire.json()["id"]


def test_hire_auto_grants_supervisor_access(client):
    company_id, owner_id, _, agent_id = setup_company(client)
    access = client.get(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/access",
        headers={"X-User-ID": owner_id},
    )
    assert access.status_code == 200
    grants = access.json()
    assert len(grants) == 1
    g = grants[0]
    assert g["user_id"] == owner_id
    assert g["can_use"] is True
    assert g["can_manage"] is True
    assert g["can_approve"] is True
    assert g["is_supervisor"] is True

    inst = client.get(
        f"/api/v1/companies/{company_id}/agents",
        headers={"X-User-ID": owner_id},
    ).json()
    row = next(i for i in inst if i["id"] == agent_id)
    assert row["supervisor_user_id"] == owner_id


def test_member_without_access_cannot_create_task(client):
    company_id, owner_id, member_id, agent_id = setup_company(client)
    resp = client.post(
        f"/api/v1/companies/{company_id}/tasks",
        headers={"X-User-ID": member_id},
        json={
            "agent_instance_id": agent_id,
            "title": "Hello",
            "instruction": "Do something",
        },
    )
    assert resp.status_code == 403


def test_member_with_use_access_can_create_task(client):
    company_id, owner_id, member_id, agent_id = setup_company(client)
    assign = client.post(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/access",
        headers={"X-User-ID": owner_id},
        json={
            "user_id": member_id,
            "can_use": True,
            "can_manage": False,
            "can_approve": False,
        },
    )
    assert assign.status_code == 201, assign.text

    resp = client.post(
        f"/api/v1/companies/{company_id}/tasks",
        headers={"X-User-ID": member_id},
        json={
            "agent_instance_id": agent_id,
            "title": "Hello",
            "instruction": "Do something",
        },
    )
    assert resp.status_code == 201, resp.text


def test_member_cannot_configure_without_manage(client):
    company_id, owner_id, member_id, agent_id = setup_company(client)
    client.post(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/access",
        headers={"X-User-ID": owner_id},
        json={"user_id": member_id, "can_use": True, "can_manage": False},
    )
    resp = client.patch(
        f"/api/v1/companies/{company_id}/agents/{agent_id}",
        headers={"X-User-ID": member_id},
        json={"instructions": "hacked"},
    )
    assert resp.status_code == 403


def test_member_with_manage_can_configure(client):
    company_id, owner_id, member_id, agent_id = setup_company(client)
    client.post(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/access",
        headers={"X-User-ID": owner_id},
        json={"user_id": member_id, "can_use": True, "can_manage": True},
    )
    resp = client.patch(
        f"/api/v1/companies/{company_id}/agents/{agent_id}",
        headers={"X-User-ID": member_id},
        json={"instructions": "Company custom instructions"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["instructions"] == "Company custom instructions"
