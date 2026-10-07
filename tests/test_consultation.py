"""Job 07 — Consultation mode tests."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.runtime.tool_executor import ToolExecutionError, ToolExecutor
from app.services.consultation import is_read_only_tool
from app.services.seed import seed_catalog

engine = create_engine(
    "sqlite:///./test_consultation.db",
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
    co = client.post("/api/v1/companies", json={"name": "Consult Co"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={"name": "Owner", "email": "owner@c.test", "role": "owner"},
    ).json()
    catalog = client.get("/api/v1/agent-catalog").json()
    res = next(i for i in catalog if i["slug"] == "reservation")
    hire = client.post(
        f"/api/v1/companies/{co['id']}/agents/{res['id']}/hire",
        json={"name": "Consult AI"},
        headers={"X-User-ID": owner["id"]},
    )
    assert hire.status_code == 201
    return co["id"], owner["id"], hire.json()["id"]


def test_is_read_only_tool():
    assert is_read_only_tool("search_availability") is True
    assert is_read_only_tool("get_reservation") is True
    assert is_read_only_tool("create_reservation") is False
    assert is_read_only_tool("send_quotation") is False


def test_create_consult_task_and_run(client):
    company_id, owner_id, agent_id = setup(client)
    # seed some knowledge for rationale
    client.post(
        f"/api/v1/companies/{company_id}/knowledge",
        headers={"X-User-ID": owner_id},
        json={
            "title": "Discount policy",
            "content": "Maximum discretionary discount is 5 percent without manager approval.",
            "category": "policy",
        },
    )

    task = client.post(
        f"/api/v1/companies/{company_id}/tasks",
        headers={"X-User-ID": owner_id},
        json={
            "agent_instance_id": agent_id,
            "title": "Discount question",
            "instruction": "Should we give this customer a 10% discount?",
            "mode": "consult",
        },
    )
    assert task.status_code == 201, task.text
    assert task.json()["mode"] == "consult"

    run = client.post(
        f"/api/v1/companies/{company_id}/tasks/{task.json()['id']}/consult",
        headers={"X-User-ID": owner_id},
    )
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["status"] == "completed"
    result = json.loads(body["result"])
    assert result["mode"] == "consult"
    assert result["side_effects_executed"] is False
    assert "recommendation" in result
    assert "rationale" in result
    assert isinstance(result.get("alternatives"), list)


def test_consult_endpoint_rejects_execute_mode(client):
    company_id, owner_id, agent_id = setup(client)
    task = client.post(
        f"/api/v1/companies/{company_id}/tasks",
        headers={"X-User-ID": owner_id},
        json={
            "agent_instance_id": agent_id,
            "title": "Do something",
            "instruction": "Create a reservation",
            "mode": "execute",
        },
    ).json()
    run = client.post(
        f"/api/v1/companies/{company_id}/tasks/{task['id']}/consult",
        headers={"X-User-ID": owner_id},
    )
    assert run.status_code == 400


def test_tool_executor_blocks_side_effect_in_consult(client):
    company_id, owner_id, agent_id = setup(client)
    task = client.post(
        f"/api/v1/companies/{company_id}/tasks",
        headers={"X-User-ID": owner_id},
        json={
            "agent_instance_id": agent_id,
            "title": "Consult only",
            "instruction": "Advise only",
            "mode": "consult",
        },
    ).json()

    with SessionLocal() as db:
        executor = ToolExecutor(db)
        with pytest.raises(ToolExecutionError) as exc:
            executor.execute(
                company_id=company_id,
                agent_instance_id=agent_id,
                tool_name="create_reservation",
                arguments={"guest": "A"},
                task_id=task["id"],
            )
        assert "consultation" in str(exc.value).lower() or "side-effect" in str(
            exc.value
        ).lower()


def test_default_mode_is_execute(client):
    company_id, owner_id, agent_id = setup(client)
    task = client.post(
        f"/api/v1/companies/{company_id}/tasks",
        headers={"X-User-ID": owner_id},
        json={
            "agent_instance_id": agent_id,
            "title": "Normal",
            "instruction": "Do work",
        },
    )
    assert task.status_code == 201
    assert task.json().get("mode", "execute") == "execute"
