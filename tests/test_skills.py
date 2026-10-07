"""Phase 4 — Skill system tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.services.seed import seed_catalog

engine = create_engine(
    "sqlite:///./test_skills.db",
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
    co = client.post("/api/v1/companies", json={"name": "Skill Co"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={"name": "Owner", "email": "owner@s.test", "role": "owner"},
    ).json()
    catalog = client.get("/api/v1/agent-catalog").json()
    res = next(i for i in catalog if i["slug"] == "reservation")
    hire = client.post(
        f"/api/v1/companies/{co['id']}/agents/{res['id']}/hire",
        json={"name": "Skill AI"},
        headers={"X-User-ID": owner["id"]},
    )
    assert hire.status_code == 201, hire.text
    return co["id"], owner["id"], hire.json()["id"]


def test_list_platform_skills(client):
    company_id, owner_id, _ = setup(client)
    resp = client.get(
        f"/api/v1/companies/{company_id}/skills",
        headers={"X-User-ID": owner_id},
    )
    assert resp.status_code == 200
    slugs = {s["slug"] for s in resp.json()}
    assert "availability_check" in slugs
    assert "contract_analysis" in slugs
    # platform skills have no company_id
    platform = [s for s in resp.json() if s["company_id"] is None]
    assert len(platform) >= 5


def test_hire_auto_assigns_matching_skills(client):
    company_id, owner_id, agent_id = setup(client)
    resp = client.get(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/skills",
        headers={"X-User-ID": owner_id},
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_create_company_skill_tenant_isolated(client):
    company_id, owner_id, _ = setup(client)
    created = client.post(
        f"/api/v1/companies/{company_id}/skills",
        headers={"X-User-ID": owner_id},
        json={
            "slug": "custom_upsell",
            "name": "Custom Upsell",
            "instructions": "Suggest upsells from company knowledge only.",
            "allowed_tools": ["search_availability"],
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["company_id"] == company_id

    # second company cannot see first company's custom skill only platform
    co2 = client.post("/api/v1/companies", json={"name": "Other Co"}).json()
    owner2 = client.post(
        f"/api/v1/companies/{co2['id']}/users",
        json={"name": "O2", "email": "o2@s.test", "role": "owner"},
    ).json()
    skills2 = client.get(
        f"/api/v1/companies/{co2['id']}/skills",
        headers={"X-User-ID": owner2["id"]},
    ).json()
    custom = [s for s in skills2 if s["slug"] == "custom_upsell"]
    assert custom == []


def test_tool_requirement_enforcement(client):
    company_id, owner_id, agent_id = setup(client)
    # create skill with tool not on agent
    skill = client.post(
        f"/api/v1/companies/{company_id}/skills",
        headers={"X-User-ID": owner_id},
        json={
            "slug": "forbidden_tool_skill",
            "name": "Forbidden",
            "allowed_tools": ["delete_everything"],
        },
    )
    assert skill.status_code == 201
    assign = client.post(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/skills",
        headers={"X-User-ID": owner_id},
        json={"skill_id": skill.json()["id"]},
    )
    assert assign.status_code == 400
    assert "not allowed" in assign.json()["detail"].lower()


def test_assign_compatible_skill(client):
    company_id, owner_id, agent_id = setup(client)
    skills = client.get(
        f"/api/v1/companies/{company_id}/skills",
        headers={"X-User-ID": owner_id},
    ).json()
    # pick a platform skill whose tools are subset of reservation agent tools
    target = next(
        s for s in skills if s["slug"] == "availability_check"
    )
    # may already be assigned at hire — second assign should be idempotent 201
    assign = client.post(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/skills",
        headers={"X-User-ID": owner_id},
        json={"skill_id": target["id"]},
    )
    assert assign.status_code == 201, assign.text
