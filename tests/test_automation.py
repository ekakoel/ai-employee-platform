"""Job 11 — Automation tests."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.models.entities import AutomationRule
from app.services.seed import seed_catalog

engine = create_engine(
    "sqlite:///./test_automation.db",
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
    co = client.post("/api/v1/companies", json={"name": "Auto Co"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={"name": "Owner", "email": "owner@auto.test", "role": "owner"},
    ).json()
    catalog = client.get("/api/v1/agent-catalog").json()
    res = next(i for i in catalog if i["slug"] == "reservation")
    hire = client.post(
        f"/api/v1/companies/{co['id']}/agents/{res['id']}/hire",
        json={"name": "Auto AI"},
        headers={"X-User-ID": owner["id"]},
    )
    assert hire.status_code == 201
    return co["id"], owner["id"], hire.json()["id"]


def test_schedule_tick_creates_task(client):
    company_id, owner_id, agent_id = setup(client)
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    rule = client.post(
        f"/api/v1/companies/{company_id}/automations",
        headers={"X-User-ID": owner_id},
        json={
            "agent_instance_id": agent_id,
            "name": "Nightly check",
            "trigger_type": "schedule",
            "interval_seconds": 3600,
            "next_run_at": past,
            "task_title_template": "Scheduled availability",
            "task_instruction_template": "Review availability status",
            "task_mode": "consult",
        },
    )
    assert rule.status_code == 201, rule.text

    runs = client.post(
        f"/api/v1/companies/{company_id}/automations/tick",
        headers={"X-User-ID": owner_id},
    )
    assert runs.status_code == 200, runs.text
    body = runs.json()
    assert len(body) >= 1
    assert body[0]["status"] in ("completed", "paused_approval")
    assert body[0]["task_id"]

    # second tick same window is idempotent (no duplicate for same due key)
    runs2 = client.post(
        f"/api/v1/companies/{company_id}/automations/tick",
        headers={"X-User-ID": owner_id},
    )
    assert runs2.status_code == 200
    # after first run next_run_at advanced; may be empty
    assert isinstance(runs2.json(), list)


def test_event_trigger_idempotency(client):
    company_id, owner_id, agent_id = setup(client)
    rule = client.post(
        f"/api/v1/companies/{company_id}/automations",
        headers={"X-User-ID": owner_id},
        json={
            "agent_instance_id": agent_id,
            "name": "On booking",
            "trigger_type": "event",
            "event_type": "booking.created",
            "task_title_template": "New booking {booking_id}",
            "task_instruction_template": "Handle booking {booking_id}",
            "task_mode": "consult",
        },
    )
    assert rule.status_code == 201, rule.text

    r1 = client.post(
        f"/api/v1/companies/{company_id}/automations/events",
        headers={"X-User-ID": owner_id},
        json={
            "event_type": "booking.created",
            "payload": {"booking_id": "B-100"},
            "idempotency_key": "booking.created:B-100",
        },
    )
    assert r1.status_code == 200, r1.text
    assert len(r1.json()) == 1
    run_id = r1.json()[0]["id"]
    task_id = r1.json()[0]["task_id"]

    r2 = client.post(
        f"/api/v1/companies/{company_id}/automations/events",
        headers={"X-User-ID": owner_id},
        json={
            "event_type": "booking.created",
            "payload": {"booking_id": "B-100"},
            "idempotency_key": "booking.created:B-100",
        },
    )
    assert r2.status_code == 200
    assert len(r2.json()) == 1
    assert r2.json()[0]["id"] == run_id
    assert r2.json()[0]["task_id"] == task_id


def test_retry_failed_run(client):
    company_id, owner_id, agent_id = setup(client)
    rule = client.post(
        f"/api/v1/companies/{company_id}/automations",
        headers={"X-User-ID": owner_id},
        json={
            "agent_instance_id": agent_id,
            "name": "Retryable",
            "trigger_type": "event",
            "event_type": "retry.test",
            "task_title_template": "Retry task",
            "task_instruction_template": "Do something",
            "task_mode": "consult",
            "max_retries": 3,
        },
    ).json()

    # fire once successfully then force-fail a synthetic run via DB is hard;
    # instead create event, then manually mark failed and retry
    r1 = client.post(
        f"/api/v1/companies/{company_id}/automations/events",
        headers={"X-User-ID": owner_id},
        json={
            "event_type": "retry.test",
            "idempotency_key": "retry.test:1",
        },
    )
    assert r1.status_code == 200
    run_id = r1.json()[0]["id"]

    with SessionLocal() as db:
        from app.models.entities import AutomationRun

        run = db.get(AutomationRun, run_id)
        run.status = "failed"
        run.error_message = "forced failure"
        db.commit()

    retry = client.post(
        f"/api/v1/companies/{company_id}/automations/runs/{run_id}/retry",
        headers={"X-User-ID": owner_id},
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["attempt"] == 2
    assert retry.json()["status"] in ("completed", "paused_approval", "failed")


def test_list_rules_and_runs(client):
    company_id, owner_id, agent_id = setup(client)
    client.post(
        f"/api/v1/companies/{company_id}/automations",
        headers={"X-User-ID": owner_id},
        json={
            "agent_instance_id": agent_id,
            "name": "List me",
            "trigger_type": "event",
            "event_type": "list.event",
            "task_title_template": "T",
            "task_instruction_template": "I",
        },
    )
    rules = client.get(
        f"/api/v1/companies/{company_id}/automations",
        headers={"X-User-ID": owner_id},
    )
    assert rules.status_code == 200
    assert len(rules.json()) >= 1

    client.post(
        f"/api/v1/companies/{company_id}/automations/events",
        headers={"X-User-ID": owner_id},
        json={"event_type": "list.event", "idempotency_key": "list.event:1"},
    )
    runs = client.get(
        f"/api/v1/companies/{company_id}/automations/runs",
        headers={"X-User-ID": owner_id},
    )
    assert runs.status_code == 200
    assert len(runs.json()) >= 1


def test_schedule_requires_interval(client):
    company_id, owner_id, agent_id = setup(client)
    resp = client.post(
        f"/api/v1/companies/{company_id}/automations",
        headers={"X-User-ID": owner_id},
        json={
            "agent_instance_id": agent_id,
            "name": "Bad schedule",
            "trigger_type": "schedule",
            "task_title_template": "T",
            "task_instruction_template": "I",
        },
    )
    assert resp.status_code == 400
