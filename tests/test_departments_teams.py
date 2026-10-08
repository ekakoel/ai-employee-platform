"""Job 18 — Departments & AI teams tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.services.seed import seed_catalog

engine = create_engine(
    "sqlite:///./test_departments_teams.db",
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
    co = client.post("/api/v1/companies", json={"name": "Org Co"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={
            "name": "Owner",
            "email": "org@test.local",
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
    return co["id"], headers, hire.json()["id"]


def test_department_crud_and_user_assign(client):
    company_id, headers, agent_id = setup(client)
    dept = client.post(
        f"/api/v1/companies/{company_id}/departments",
        headers=headers,
        json={"name": "Sales", "description": "Sales dept"},
    )
    assert dept.status_code == 201, dept.text
    dept_id = dept.json()["id"]

    listed = client.get(
        f"/api/v1/companies/{company_id}/departments",
        headers=headers,
    )
    assert listed.status_code == 200
    assert any(d["id"] == dept_id for d in listed.json())

    user = client.post(
        f"/api/v1/companies/{company_id}/users",
        headers=headers,
        json={
            "name": "Sales User",
            "email": "sales@test.local",
            "role": "member",
            "department_id": dept_id,
        },
    )
    assert user.status_code == 201, user.text
    assert user.json()["department_id"] == dept_id


def test_agent_team_and_members(client):
    company_id, headers, agent_id = setup(client)
    dept = client.post(
        f"/api/v1/companies/{company_id}/departments",
        headers=headers,
        json={"name": "Ops"},
    ).json()
    team = client.post(
        f"/api/v1/companies/{company_id}/teams",
        headers=headers,
        json={
            "name": "Front Desk Team",
            "department_id": dept["id"],
            "agent_instance_ids": [agent_id],
        },
    )
    assert team.status_code == 201, team.text
    body = team.json()
    assert body["department_id"] == dept["id"]
    assert agent_id in body["member_agent_ids"]

    teams = client.get(
        f"/api/v1/companies/{company_id}/teams",
        headers=headers,
    )
    assert teams.status_code == 200
    assert len(teams.json()) >= 1


def test_department_tenant_isolation(client):
    a_id, a_headers, _ = setup(client)
    # second company
    co2 = client.post("/api/v1/companies", json={"name": "Other Org"}).json()
    owner2 = client.post(
        f"/api/v1/companies/{co2['id']}/users",
        json={
            "name": "O2",
            "email": "o2@test.local",
            "role": "owner",
            "password": "secret123",
        },
    ).json()
    dept = client.post(
        f"/api/v1/companies/{a_id}/departments",
        headers=a_headers,
        json={"name": "Finance"},
    ).json()
    # user from co2 cannot list co1 departments
    bad = client.get(
        f"/api/v1/companies/{a_id}/departments",
        headers={"X-User-ID": owner2["id"]},
    )
    assert bad.status_code == 403

    # cannot assign foreign department to co2 user
    bad_user = client.post(
        f"/api/v1/companies/{co2['id']}/users",
        headers={"X-User-ID": owner2["id"]},
        json={
            "name": "X",
            "email": "x@test.local",
            "role": "member",
            "department_id": dept["id"],
        },
    )
    assert bad_user.status_code in (400, 422)


def test_filter_agents_by_department(client):
    company_id, headers, agent_id = setup(client)
    dept = client.post(
        f"/api/v1/companies/{company_id}/departments",
        headers=headers,
        json={"name": "Reservations"},
    ).json()
    # assign agent to department via patch
    upd = client.patch(
        f"/api/v1/companies/{company_id}/agents/{agent_id}",
        headers=headers,
        json={"department_id": dept["id"]},
    )
    assert upd.status_code == 200, upd.text
    assert upd.json().get("department_id") == dept["id"]

    filtered = client.get(
        f"/api/v1/companies/{company_id}/agents",
        headers=headers,
        params={"department_id": dept["id"]},
    )
    assert filtered.status_code == 200
    ids = [a["id"] for a in filtered.json()]
    assert agent_id in ids

    empty = client.get(
        f"/api/v1/companies/{company_id}/agents",
        headers=headers,
        params={"department_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert empty.status_code == 200
    assert empty.json() == []
