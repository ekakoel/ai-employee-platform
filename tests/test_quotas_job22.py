"""Job 22 — Plans, quotas, usage metering tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.services.quotas import set_company_plan
from app.services.seed import seed_catalog

engine = create_engine(
    "sqlite:///./test_quotas_job22.db",
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
    co = client.post("/api/v1/companies", json={"name": "Quota Co"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={
            "name": "Owner",
            "email": "quota@test.local",
            "role": "owner",
            "password": "secret123",
        },
    ).json()
    headers = {"X-User-ID": owner["id"]}
    return co["id"], headers


def test_list_plans_and_default_usage(client):
    company_id, headers = setup(client)
    plans = client.get("/api/v1/plans")
    assert plans.status_code == 200
    codes = {p["code"] for p in plans.json()}
    assert "free" in codes
    assert "pro" in codes

    usage = client.get(
        f"/api/v1/companies/{company_id}/usage",
        headers=headers,
    )
    assert usage.status_code == 200
    body = usage.json()
    assert body["plan"]["code"] == "free"
    assert body["usage"]["agents"] == 0


def test_agent_quota_exceeded(client):
    company_id, headers = setup(client)
    # free max_agents=3 — hire until blocked
    catalog = client.get("/api/v1/agent-catalog").json()
    res = next(i for i in catalog if i["slug"] == "reservation")
    for i in range(3):
        r = client.post(
            f"/api/v1/companies/{company_id}/agents/{res['id']}/hire",
            json={"name": f"Agent {i}"},
            headers=headers,
        )
        assert r.status_code == 201, r.text
    blocked = client.post(
        f"/api/v1/companies/{company_id}/agents/{res['id']}/hire",
        json={"name": "Agent over"},
        headers=headers,
    )
    assert blocked.status_code == 429
    detail = blocked.json()["detail"]
    assert detail["error"] == "quota_exceeded"
    assert detail["metric"] == "max_agents"


def test_task_quota_and_upgrade_plan(client):
    company_id, headers = setup(client)
    catalog = client.get("/api/v1/agent-catalog").json()
    res = next(i for i in catalog if i["slug"] == "reservation")
    hire = client.post(
        f"/api/v1/companies/{company_id}/agents/{res['id']}/hire",
        json={"name": "Desk"},
        headers=headers,
    )
    agent_id = hire.json()["id"]

    # shrink free plan tasks for test via direct set + low limit plan
    # use free plan but set max via assign and manual - create many tasks up to limit is slow
    # instead: set plan and force usage by creating tasks equal to limit
    # Assign enterprise then we won't hit - assign free and temporarily lower by API not available
    # Simpler: create tasks until free max_tasks_day (50) is heavy - instead patch plan in DB
    with SessionLocal() as db:
        from app.models.entities import Plan
        from sqlalchemy import select
        free = db.scalar(select(Plan).where(Plan.code == "free"))
        free.max_tasks_day = 2
        db.commit()

    for i in range(2):
        t = client.post(
            f"/api/v1/companies/{company_id}/tasks",
            headers=headers,
            json={
                "agent_instance_id": agent_id,
                "title": f"T{i}",
                "instruction": "do",
                "mode": "consult",
            },
        )
        assert t.status_code == 201, t.text

    blocked = client.post(
        f"/api/v1/companies/{company_id}/tasks",
        headers=headers,
        json={
            "agent_instance_id": agent_id,
            "title": "T over",
            "instruction": "do",
            "mode": "consult",
        },
    )
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["metric"] == "max_tasks_day"

    # upgrade to pro
    up = client.put(
        f"/api/v1/companies/{company_id}/plan",
        headers=headers,
        json={"plan_code": "pro"},
    )
    assert up.status_code == 200
    assert up.json()["plan"]["code"] == "pro"

    ok = client.post(
        f"/api/v1/companies/{company_id}/tasks",
        headers=headers,
        json={
            "agent_instance_id": agent_id,
            "title": "After upgrade",
            "instruction": "do",
            "mode": "consult",
        },
    )
    assert ok.status_code == 201
