from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.entities import AgentInstance, Approval, AuditLog, Company, DelegationRequest, Task, User
from app.services.seed import get_or_create_role


@pytest.fixture
def inbox_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        owner = get_or_create_role(db, "owner")
        member = get_or_create_role(db, "member")
        db.add_all([Company(id="one", name="One"), Company(id="two", name="Two")])
        db.flush()
        db.add_all([
            User(id="alice", company_id="one", name="Alice", email="alice@test.local", role_id=owner.id),
            User(id="member", company_id="one", name="Member", email="member@test.local", role_id=member.id),
            User(id="eve", company_id="two", name="Private name", email="eve@test.local", role_id=owner.id),
            AgentInstance(id="agent", company_id="one", name="Analyst", catalog_agent_id="catalog", subscription_id="subscription"),
        ])
        db.flush()
        db.add_all([
            Task(id=task_id, company_id=company, agent_instance_id="agent", title=task_id, instruction="Work", status=state)
            for task_id, company, state in [("task", "one", "pending"), ("done", "one", "completed"), ("foreign", "two", "pending"), ("unknown", "one", "failed"), ("legacy", "one", "pending")]
        ])
        db.add(Approval(id="approval", company_id="one", task_id="task", agent_instance_id="agent", action="Refund", reason="Review", status="pending"))
        db.add(DelegationRequest(id="handoff", company_id="one", source_agent_instance_id="agent", target_agent_instance_id="agent", capability="research", title="Research", instruction="Work", status="accepted"))
        db.flush()
        events = [
            ("old", "one", "task", "task", "task.create", "alice", "agent", 1),
            ("latest", "one", "task", "task", "task.planning", None, "agent", 2),
            ("done-log", "one", "task", "done", "task.completed", None, "agent", 3),
            ("foreign-log", "two", "task", "foreign", "task.create", "eve", None, 4),
            ("bad-tenant", "two", "task", "task", "task.create", "eve", None, 5),
            ("unknown-log", "one", "task", "unknown", "task.failed", None, None, 2),
            ("approval-log", "one", "approval", "approval", "approval.requested", None, "agent", 2),
            ("handoff-log", "one", "delegation_request", "handoff", "delegation.accept", "alice", "agent", 2),
        ]
        for event_id, company, resource, resource_id, action, human, agent, hour in events:
            db.add(AuditLog(id=event_id, company_id=company, resource_type=resource, resource_id=resource_id,
                action=action, user_id=human, agent_instance_id=agent, status="success",
                created_at=datetime(2026, 10, 9, hour, tzinfo=timezone.utc)))
        db.commit()

    def override():
        with sessions() as db:
            yield db

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override
    try:
        yield TestClient(app)
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous
        engine.dispose()


def test_latest_event_is_scoped_and_utc(inbox_client):
    response = inbox_client.get("/api/v1/companies/one/inbox-attribution/task", headers={"X-User-ID": "member"})
    assert response.status_code == 200
    rows = {row["resource_id"]: row for row in response.json()}
    assert set(rows) == {"task", "unknown"}
    assert rows["task"]["actor_name"] == "Analyst"
    assert rows["task"]["actor_type"] == "agent"
    assert rows["task"]["action"] == "task.planning"
    assert rows["task"]["performed_at"] == "2026-10-09T02:00:00Z"
    assert rows["unknown"]["actor_type"] == "unknown"
    assert rows["unknown"]["actor_name"] == "Actor not recorded"
    assert "details" not in rows["task"]


def test_human_actor_takes_precedence_over_assigned_agent(inbox_client):
    headers = {"X-User-ID": "alice"}
    handoff = inbox_client.get("/api/v1/companies/one/inbox-attribution/delegation", headers=headers).json()[0]
    assert (handoff["actor_type"], handoff["actor_name"]) == ("human", "Alice")
    approval = inbox_client.get("/api/v1/companies/one/inbox-attribution/approval", headers=headers).json()[0]
    assert (approval["actor_type"], approval["actor_name"]) == ("agent", "Analyst")


def test_attribution_keeps_resource_permissions_and_tenant_boundaries(inbox_client):
    path = "/api/v1/companies/one/inbox-attribution/"
    assert inbox_client.get(path + "task").status_code in (401, 403)
    assert inbox_client.get(path + "task", headers={"X-User-ID": "eve"}).status_code == 403
    assert inbox_client.get(path + "approval", headers={"X-User-ID": "member"}).status_code == 403
    assert inbox_client.get(path + "delegation", headers={"X-User-ID": "member"}).status_code == 200
    assert inbox_client.get(path + "unsupported", headers={"X-User-ID": "alice"}).status_code == 422
