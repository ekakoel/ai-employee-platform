"""Job 27 — Multi-step automation workflow tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.models.entities import Approval, ApprovalStatus, Task, TaskStatus, WorkflowRunStatus
from app.services.seed import seed_catalog
from app.services.workflow import advance_run, resume_run

engine = create_engine(
    "sqlite:///./test_workflow_job27.db",
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
    co = client.post("/api/v1/companies", json={"name": "WF Co"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={
            "name": "Owner",
            "email": "wf@test.local",
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


def test_workflow_happy_path(client):
    company_id, headers, agent_id = setup(client)
    wf = client.post(
        f"/api/v1/companies/{company_id}/workflows",
        headers=headers,
        json={
            "name": "Daily briefing",
            "steps": [
                {
                    "type": "create_task",
                    "agent_instance_id": agent_id,
                    "title": "Briefing",
                    "instruction": "Summarize open items",
                    "mode": "consult",
                    "auto_run": False,
                },
                {"type": "emit_event", "event_type": "briefing.done"},
                {"type": "complete"},
            ],
        },
    )
    assert wf.status_code == 201, wf.text
    wid = wf.json()["id"]

    run = client.post(
        f"/api/v1/companies/{company_id}/workflows/{wid}/runs",
        headers=headers,
        json={"context": {}},
    )
    assert run.status_code == 201, run.text
    body = run.json()
    assert body["status"] == WorkflowRunStatus.COMPLETED.value
    assert body["current_step"] >= 2
    assert any(r.get("task_id") for r in body["step_results"])


def test_workflow_pause_on_approval_and_resume(client):
    company_id, headers, agent_id = setup(client)
    wf = client.post(
        f"/api/v1/companies/{company_id}/workflows",
        headers=headers,
        json={
            "name": "Approve path",
            "steps": [
                {
                    "type": "create_task",
                    "agent_instance_id": agent_id,
                    "title": "Needs approval later",
                    "instruction": "hold",
                    "mode": "consult",
                    "auto_run": False,
                },
                {"type": "wait_approval"},
                {"type": "emit_event", "event_type": "approved.done"},
                {"type": "complete"},
            ],
        },
    )
    wid = wf.json()["id"]
    run = client.post(
        f"/api/v1/companies/{company_id}/workflows/{wid}/runs",
        headers=headers,
        json={},
    )
    assert run.status_code == 201, run.text
    # Force task into waiting_approval + pending approval
    run_id = run.json()["id"]
    task_id = None
    for r in run.json()["step_results"]:
        if r.get("task_id"):
            task_id = r["task_id"]
            break
    assert task_id

    with SessionLocal() as db:
        task = db.get(Task, task_id)
        task.status = TaskStatus.WAITING_APPROVAL.value
        approval = Approval(
            company_id=company_id,
            task_id=task_id,
            agent_instance_id=agent_id,
            action="tool.x",
            reason="test",
            payload={},
            status=ApprovalStatus.PENDING.value,
        )
        db.add(approval)
        db.commit()
        approval_id = approval.id

        run_row = db.get(
            __import__("app.models.entities", fromlist=["WorkflowRun"]).WorkflowRun,
            run_id,
        )
        # advance into wait_approval pause
        run_row.current_step = 1
        run_row.status = WorkflowRunStatus.RUNNING.value
        db.commit()
        run_row = resume_run(db, run=run_row)
        db.commit()
        assert run_row.status == WorkflowRunStatus.PAUSED_APPROVAL.value

        # approve
        approval = db.get(Approval, approval_id)
        approval.status = ApprovalStatus.APPROVED.value
        task = db.get(Task, task_id)
        task.status = TaskStatus.COMPLETED.value
        db.commit()

        run_row = resume_run(db, run=run_row)
        db.commit()
        assert run_row.status == WorkflowRunStatus.COMPLETED.value


def test_workflow_fail_missing_agent(client):
    company_id, headers, agent_id = setup(client)
    wf = client.post(
        f"/api/v1/companies/{company_id}/workflows",
        headers=headers,
        json={
            "name": "Bad agent",
            "steps": [
                {
                    "type": "create_task",
                    "agent_instance_id": "00000000-0000-0000-0000-000000000000",
                    "title": "x",
                    "instruction": "y",
                    "auto_run": False,
                },
                {"type": "complete"},
            ],
        },
    )
    run = client.post(
        f"/api/v1/companies/{company_id}/workflows/{wf.json()['id']}/runs",
        headers=headers,
        json={},
    )
    assert run.status_code == 201
    assert run.json()["status"] == WorkflowRunStatus.FAILED.value


def test_invalid_step_type(client):
    company_id, headers, agent_id = setup(client)
    bad = client.post(
        f"/api/v1/companies/{company_id}/workflows",
        headers=headers,
        json={
            "name": "Bad",
            "steps": [{"type": "explode"}],
        },
    )
    assert bad.status_code == 400
