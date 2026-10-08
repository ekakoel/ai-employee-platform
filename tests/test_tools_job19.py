"""Job 19 — Tool catalog expansion + connector + side-effect classification."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.runtime.tool_executor import ToolExecutionError, ToolExecutor
from app.services.seed import seed_catalog
from app.tools.connectors import MockExternalSystemClient, set_external_client
from app.tools.domain import build_default_tools
from app.tools.registry import ToolRegistry

engine = create_engine(
    "sqlite:///./test_tools_job19.db",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_catalog(db)
    set_external_client(MockExternalSystemClient())

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
    co = client.post("/api/v1/companies", json={"name": "Tool Co"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={
            "name": "Owner",
            "email": "tools@test.local",
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


def test_tool_catalog_endpoint(client):
    resp = client.get("/api/v1/tools")
    assert resp.status_code == 200, resp.text
    names = {t["name"] for t in resp.json()}
    assert "search_contract" in names
    assert "search_availability" in names
    assert "create_reservation" in names
    assert "search_knowledge" in names
    assert "draft_quotation" in names
    create = next(t for t in resp.json() if t["name"] == "create_reservation")
    assert create["side_effect"] is True
    assert create["read_only"] is False
    search = next(t for t in resp.json() if t["name"] == "search_availability")
    assert search["side_effect"] is False
    assert search["read_only"] is True


def test_side_effect_classification():
    with SessionLocal() as db:
        tools = {t.name: t for t in build_default_tools(db)}
    assert tools["create_reservation"].side_effect is True
    assert tools["search_availability"].side_effect is False
    assert tools["get_reservation"].side_effect is False
    assert tools["draft_quotation"].side_effect is False


def test_create_reservation_via_executor(client):
    company_id, headers, agent_id = setup(client)
    # allow create_reservation on agent
    client.patch(
        f"/api/v1/companies/{company_id}/agents/{agent_id}",
        headers=headers,
        json={},
    )
    with SessionLocal() as db:
        agent = db.get(
            __import__("app.models.entities", fromlist=["AgentInstance"]).AgentInstance,
            agent_id,
        )
        tools = list(agent.allowed_tools or [])
        if "create_reservation" not in tools:
            tools.append("create_reservation")
        agent.allowed_tools = tools
        db.commit()

    task = client.post(
        f"/api/v1/companies/{company_id}/tasks",
        headers=headers,
        json={
            "agent_instance_id": agent_id,
            "title": "Book room",
            "instruction": "Create reservation",
            "mode": "execute",
        },
    )
    assert task.status_code == 201
    tid = task.json()["id"]

    with SessionLocal() as db:
        ex = ToolExecutor(db)
        result = ex.execute(
            company_id=company_id,
            agent_instance_id=agent_id,
            tool_name="create_reservation",
            arguments={
                "guest_name": "Ada",
                "check_in": "2026-11-01",
                "check_out": "2026-11-03",
            },
            task_id=tid,
        )
        assert result["reservation_id"]
        assert result["side_effect"] is True


def test_consult_blocks_side_effect_tool(client):
    company_id, headers, agent_id = setup(client)
    with SessionLocal() as db:
        agent = db.get(
            __import__("app.models.entities", fromlist=["AgentInstance"]).AgentInstance,
            agent_id,
        )
        tools = list(agent.allowed_tools or [])
        if "create_reservation" not in tools:
            tools.append("create_reservation")
        agent.allowed_tools = tools
        db.commit()

    task = client.post(
        f"/api/v1/companies/{company_id}/tasks",
        headers=headers,
        json={
            "agent_instance_id": agent_id,
            "title": "Consult book",
            "instruction": "Should I create a reservation?",
            "mode": "consult",
        },
    )
    tid = task.json()["id"]
    with SessionLocal() as db:
        ex = ToolExecutor(db)
        with pytest.raises(ToolExecutionError) as ei:
            ex.execute(
                company_id=company_id,
                agent_instance_id=agent_id,
                tool_name="create_reservation",
                arguments={
                    "guest_name": "Ada",
                    "check_in": "2026-11-01",
                    "check_out": "2026-11-03",
                },
                task_id=tid,
            )
        assert "consultation" in str(ei.value).lower() or "side-effect" in str(ei.value).lower()


def test_search_availability_allowed_in_consult(client):
    company_id, headers, agent_id = setup(client)
    task = client.post(
        f"/api/v1/companies/{company_id}/tasks",
        headers=headers,
        json={
            "agent_instance_id": agent_id,
            "title": "Avail",
            "instruction": "Check availability",
            "mode": "consult",
        },
    )
    tid = task.json()["id"]
    with SessionLocal() as db:
        agent = db.get(
            __import__("app.models.entities", fromlist=["AgentInstance"]).AgentInstance,
            agent_id,
        )
        tools = list(agent.allowed_tools or [])
        if "search_availability" not in tools:
            tools.append("search_availability")
            agent.allowed_tools = tools
            db.commit()

        ex = ToolExecutor(db)
        result = ex.execute(
            company_id=company_id,
            agent_instance_id=agent_id,
            tool_name="search_availability",
            arguments={"check_in": "2026-11-01", "check_out": "2026-11-03"},
            task_id=tid,
        )
        assert result["count"] >= 1
