"""Phase 4 — Skill system tests."""

import pytest
from fastapi.testclient import TestClient

from tests.helpers import owner_setup, provision_company, bootstrap_demo, login_headers
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
    company_id, owner_id, headers, demo = provision_company(client, hire_agents=False)
    catalog = client.get("/api/v1/agent-catalog", headers=headers).json()
    res = next(i for i in catalog if i["slug"] == "reservation")
    hire = client.post(
        f"/api/v1/companies/{company_id}/agents/{res["id"]}/hire",
        json={"name": "Skill AI"},
        headers=headers,
    )
    assert hire.status_code == 201, hire.text
    return company_id, owner_id, hire.json()["id"], headers




def test_list_platform_skills(client):
    company_id, owner_id, _, headers = setup(client)
    resp = client.get(
        f"/api/v1/companies/{company_id}/skills",
        headers=headers,
    )
    assert resp.status_code == 200
    slugs = {s["slug"] for s in resp.json()}
    assert "availability_check" in slugs
    assert "contract_analysis" in slugs
    # platform skills have no company_id
    platform = [s for s in resp.json() if s["company_id"] is None]
    assert len(platform) >= 5


def test_hire_auto_assigns_matching_skills(client):
    company_id, owner_id, agent_id, headers = setup(client)
    resp = client.get(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/skills",
        headers=headers,
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_create_company_skill_tenant_isolated(client):
    """Company roles may not create/upgrade skill catalog (platform-only)."""
    company_id, owner_id, agent_id, headers = setup(client)
    skill = client.post(
        f"/api/v1/companies/{company_id}/skills",
        headers=headers,
        json={
            "name": "Custom Upsell",
            "slug": "custom_upsell",
            "description": "Demo",
            "allowed_tools": [],
        },
    )
    assert skill.status_code in (403, 401), skill.text



def test_tool_requirement_enforcement(client):
    """Creating a skill with tools not on the agent is rejected (or skill create forbidden)."""
    company_id, owner_id, agent_id, headers = setup(client)
    skill = client.post(
        f"/api/v1/companies/{company_id}/skills",
        headers=headers,
        json={
            "name": "Forbidden Tool Skill",
            "slug": "forbidden_tool_skill",
            "description": "Needs draft_quotation",
            "allowed_tools": ["draft_quotation"],
        },
    )
    # Platform-only skill create → 403; if create allowed, assign must 400/403
    if skill.status_code == 201:
        assign = client.post(
            f"/api/v1/companies/{company_id}/agents/{agent_id}/skills",
            headers=headers,
            json={"skill_id": skill.json()["id"]},
        )
        assert assign.status_code in (400, 403), assign.text
    else:
        assert skill.status_code in (403, 401), skill.text



def test_assign_compatible_skill(client):
    company_id, owner_id, agent_id, headers = setup(client)
    skills = client.get(
        f"/api/v1/companies/{company_id}/skills",
        headers=headers,
    ).json()
    # pick a platform skill whose tools are subset of reservation agent tools
    target = next(
        s for s in skills if s["slug"] == "availability_check"
    )
    # may already be assigned at hire — second assign should be idempotent 201
    assign = client.post(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/skills",
        headers=headers,
        json={"skill_id": target["id"]},
    )
    assert assign.status_code == 201, assign.text
