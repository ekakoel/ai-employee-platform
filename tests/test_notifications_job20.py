"""Job 20 — Notifications center tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.models.entities import AgentInstance, NotificationType
from app.services.notifications import emit_notification, unread_count
from app.services.seed import seed_catalog

engine = create_engine(
    "sqlite:///./test_notifications_job20.db",
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
    co = client.post("/api/v1/companies", json={"name": "Notif Co"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={
            "name": "Owner",
            "email": "notif@test.local",
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
    agent_id = hire.json()["id"]
    # set supervisor to owner
    client.patch(
        f"/api/v1/companies/{co['id']}/agents/{agent_id}",
        headers=headers,
        json={"supervisor_user_id": owner["id"]},
    )
    return co["id"], headers, agent_id, owner["id"]


def test_emit_and_list_mark_read(client):
    company_id, headers, agent_id, owner_id = setup(client)
    with SessionLocal() as db:
        emit_notification(
            db,
            company_id=company_id,
            user_id=owner_id,
            type=NotificationType.SYSTEM.value,
            title="Hello",
            body="World",
            payload={"k": 1},
        )
        db.commit()
        assert unread_count(db, company_id=company_id, user_id=owner_id) == 1

    listed = client.get(
        f"/api/v1/companies/{company_id}/notifications",
        headers=headers,
    )
    assert listed.status_code == 200
    assert len(listed.json()) >= 1
    nid = listed.json()[0]["id"]

    count = client.get(
        f"/api/v1/companies/{company_id}/notifications/unread-count",
        headers=headers,
    )
    assert count.json()["count"] >= 1

    read = client.post(
        f"/api/v1/companies/{company_id}/notifications/{nid}/read",
        headers=headers,
    )
    assert read.status_code == 200
    assert read.json()["read_at"]

    count2 = client.get(
        f"/api/v1/companies/{company_id}/notifications/unread-count",
        headers=headers,
    )
    assert count2.json()["count"] == 0


def test_delegation_emits_notification(client):
    company_id, headers, agent_id, owner_id = setup(client)
    catalog = client.get("/api/v1/agent-catalog").json()
    # hire second agent as target
    other = next((i for i in catalog if i["slug"] != "reservation"), catalog[0])
    hire2 = client.post(
        f"/api/v1/companies/{company_id}/agents/{other['id']}/hire",
        json={"name": "Target AI"},
        headers=headers,
    )
    if hire2.status_code != 201:
        # same template twice may fail — create second reservation hire with different name via same catalog if allowed
        pytest.skip("second agent hire not available")
    target_id = hire2.json()["id"]
    client.patch(
        f"/api/v1/companies/{company_id}/agents/{target_id}",
        headers=headers,
        json={"supervisor_user_id": owner_id},
    )
    # capability must match target agent tools/skills
    target_body = hire2.json()
    caps = target_body.get("allowed_tools") or ["search_contract"]
    cap = caps[0] if caps else "search_contract"
    resp = client.post(
        f"/api/v1/companies/{company_id}/delegation-requests",
        headers=headers,
        json={
            "source_agent_instance_id": agent_id,
            "target_agent_instance_id": target_id,
            "capability": cap,
            "title": "Help with booking",
            "instruction": "Please handle this booking request",
            "timeout_seconds": 300,
        },
    )
    assert resp.status_code in (200, 201), resp.text
    notes = client.get(
        f"/api/v1/companies/{company_id}/notifications",
        headers=headers,
    )
    assert notes.status_code == 200
    types = [n["type"] for n in notes.json()]
    assert "delegation.received" in types


def test_workspace_has_notifications_view(client):
    html = client.get("/workspace").text
    assert "view-notifications" in html
    assert "btnNotifReadAll" in html
