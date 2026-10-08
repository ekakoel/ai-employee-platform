"""Job 21 — Agent conversation / chat transcript tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.services.seed import seed_catalog

engine = create_engine(
    "sqlite:///./test_conversation_job21.db",
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
    co = client.post("/api/v1/companies", json={"name": "Chat Co"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={
            "name": "Owner",
            "email": "chat@test.local",
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


def test_conversation_flow(client):
    company_id, headers, agent_id = setup(client)
    conv = client.post(
        f"/api/v1/companies/{company_id}/conversations",
        headers=headers,
        json={"agent_instance_id": agent_id, "title": "Help"},
    )
    assert conv.status_code == 201, conv.text
    cid = conv.json()["id"]

    msgs = client.get(
        f"/api/v1/companies/{company_id}/conversations/{cid}/messages",
        headers=headers,
    )
    assert msgs.status_code == 200
    assert any(m["role"] == "system" for m in msgs.json())

    post = client.post(
        f"/api/v1/companies/{company_id}/conversations/{cid}/messages",
        headers=headers,
        json={"content": "What is available next week?", "create_task": False},
    )
    assert post.status_code == 200, post.text
    body = post.json()
    assert body["human"]["role"] == "human"
    assert body["agent"]["role"] == "agent"
    assert body["task_id"] is None

    post2 = client.post(
        f"/api/v1/companies/{company_id}/conversations/{cid}/messages",
        headers=headers,
        json={
            "content": "Create a reservation for Ada",
            "create_task": True,
            "task_mode": "consult",
        },
    )
    assert post2.status_code == 200, post2.text
    assert post2.json()["task_id"]
    # task exists
    tasks = client.get(
        f"/api/v1/companies/{company_id}/tasks",
        headers=headers,
    )
    assert any(t["id"] == post2.json()["task_id"] for t in tasks.json())


def test_tenant_isolation(client):
    company_id, headers, agent_id = setup(client)
    conv = client.post(
        f"/api/v1/companies/{company_id}/conversations",
        headers=headers,
        json={"agent_instance_id": agent_id, "title": "Private"},
    ).json()
    # other company
    co2 = client.post("/api/v1/companies", json={"name": "Other Chat"}).json()
    owner2 = client.post(
        f"/api/v1/companies/{co2['id']}/users",
        json={
            "name": "O2",
            "email": "o2chat@test.local",
            "role": "owner",
            "password": "secret123",
        },
    ).json()
    bad = client.get(
        f"/api/v1/companies/{company_id}/conversations/{conv['id']}/messages",
        headers={"X-User-ID": owner2["id"]},
    )
    assert bad.status_code == 403


def test_workspace_has_chat(client):
    html = client.get("/workspace").text
    assert "view-chat" in html
    assert "btnChatSend" in html
