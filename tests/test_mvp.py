
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.services.seed import seed_catalog


engine = create_engine(
    "sqlite:///./test_ai_employee.db",
    connect_args={"check_same_thread": False},
)

TestingSessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

with TestingSessionLocal() as db:
    seed_catalog(db)


def override_get_db():
    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def isolate_database_override():
    previous_override = app.dependency_overrides.get(get_db)

    app.dependency_overrides[get_db] = override_get_db

    try:
        yield
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override


client = TestClient(app)


def make_company_and_owner(name: str):
    company = client.post(
        "/api/v1/companies",
        json={"name": name},
    )

    assert company.status_code == 201

    company_data = company.json()

    owner = client.post(
        f"/api/v1/companies/{company_data['id']}/users",
        json={
            "name": "Owner",
            "email": f"{name.lower().replace(' ', '.')}@test.local",
            "role": "owner",
        },
    )

    assert owner.status_code == 201

    return company_data, owner.json()


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_company_hires_agent_and_can_create_task_and_audit():
    company, owner = make_company_and_owner("Bali Kami Test")

    headers = {
        "X-User-ID": owner["id"],
    }

    catalog = client.get(
        "/api/v1/agent-catalog"
    ).json()

    reservation = next(
        x for x in catalog
        if x["slug"] == "reservation"
    )

    hired = client.post(
        f"/api/v1/companies/{company['id']}/agents/{reservation['id']}/hire",
        json={
            "name": "Reservation Agent Bali Kami",
        },
        headers=headers,
    )

    assert hired.status_code == 201

    agent_id = hired.json()["id"]
    subscription_id = hired.json()["subscription_id"]

    subscriptions = client.get(
        f"/api/v1/companies/{company['id']}/subscriptions",
        headers=headers,
    )

    assert subscriptions.status_code == 200
    assert subscriptions.json()[0]["id"] == subscription_id

    task = client.post(
        f"/api/v1/companies/{company['id']}/tasks",
        json={
            "agent_instance_id": agent_id,
            "title": "Check booking",
            "instruction": "Check availability",
        },
        headers=headers,
    )

    assert task.status_code == 201

    audit = client.get(
        f"/api/v1/companies/{company['id']}/audit-logs",
        headers=headers,
    )

    assert audit.status_code == 200

    actions = [
        item["action"]
        for item in audit.json()
    ]

    assert "agent.hire" in actions
    assert "task.create" in actions


def test_company_cannot_create_task_with_other_company_agent():
    company_a, owner_a = make_company_and_owner("Company A")
    company_b, owner_b = make_company_and_owner("Company B")

    reservation = next(
        x
        for x in client.get(
            "/api/v1/agent-catalog"
        ).json()
        if x["slug"] == "reservation"
    )

    headers_a = {
        "X-User-ID": owner_a["id"],
    }

    headers_b = {
        "X-User-ID": owner_b["id"],
    }

    hired = client.post(
        f"/api/v1/companies/{company_b['id']}/agents/{reservation['id']}/hire",
        json={
            "name": "Company B Reservation",
        },
        headers=headers_b,
    ).json()

    response = client.post(
        f"/api/v1/companies/{company_a['id']}/tasks",
        json={
            "agent_instance_id": hired["id"],
            "title": "Forbidden",
            "instruction": "Should fail",
        },
        headers=headers_a,
    )

    assert response.status_code == 403


def test_user_cannot_access_another_company():
    company_a, owner_a = make_company_and_owner("Tenant A")
    company_b, _ = make_company_and_owner("Tenant B")

    response = client.get(
        f"/api/v1/companies/{company_b['id']}/agents",
        headers={
            "X-User-ID": owner_a["id"],
        },
    )

    assert response.status_code == 403


def test_cancelling_subscription_deactivates_agent():
    company, owner = make_company_and_owner(
        "Subscription Company"
    )

    headers = {
        "X-User-ID": owner["id"],
    }

    reservation = next(
        x
        for x in client.get(
            "/api/v1/agent-catalog"
        ).json()
        if x["slug"] == "reservation"
    )

    hired = client.post(
        f"/api/v1/companies/{company['id']}/agents/{reservation['id']}/hire",
        json={
            "name": "Reservation Subscription Test",
        },
        headers=headers,
    )

    assert hired.status_code == 201

    data = hired.json()

    cancelled = client.post(
        f"/api/v1/companies/{company['id']}/subscriptions/{data['subscription_id']}/cancel",
        headers=headers,
    )

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    agents = client.get(
        f"/api/v1/companies/{company['id']}/agents",
        headers=headers,
    )

    assert agents.status_code == 200
    assert agents.json()[0]["status"] == "inactive"


def test_cancelled_agent_cannot_receive_new_task():
    company, owner = make_company_and_owner(
        "Cancelled Agent Company"
    )

    headers = {
        "X-User-ID": owner["id"],
    }

    reservation = next(
        x
        for x in client.get(
            "/api/v1/agent-catalog"
        ).json()
        if x["slug"] == "reservation"
    )

    hired = client.post(
        f"/api/v1/companies/{company['id']}/agents/{reservation['id']}/hire",
        json={
            "name": "Inactive Reservation",
        },
        headers=headers,
    ).json()

    client.post(
        f"/api/v1/companies/{company['id']}/subscriptions/{hired['subscription_id']}/cancel",
        headers=headers,
    )

    response = client.post(
        f"/api/v1/companies/{company['id']}/tasks",
        json={
            "agent_instance_id": hired["id"],
            "title": "Must fail",
            "instruction": "Do not run",
        },
        headers=headers,
    )

    assert response.status_code == 409


def test_company_cannot_access_another_company_knowledge():
    company_a, owner_a = make_company_and_owner(
        "Knowledge Company A"
    )

    company_b, owner_b = make_company_and_owner(
        "Knowledge Company B"
    )

    headers_a = {
        "X-User-ID": owner_a["id"],
    }

    headers_b = {
        "X-User-ID": owner_b["id"],
    }

    knowledge_a = client.post(
        f"/api/v1/companies/{company_a['id']}/knowledge",
        json={
            "title": "Company A Policy",
            "content": "This knowledge belongs to Company A.",
            "category": "general",
        },
        headers=headers_a,
    )

    assert knowledge_a.status_code == 201

    knowledge_b = client.post(
        f"/api/v1/companies/{company_b['id']}/knowledge",
        json={
            "title": "Company B Policy",
            "content": "This knowledge belongs to Company B.",
            "category": "general",
        },
        headers=headers_b,
    )

    assert knowledge_b.status_code == 201

    response = client.get(
        f"/api/v1/companies/{company_a['id']}/knowledge",
        headers=headers_a,
    )

    assert response.status_code == 200

    knowledge_items = response.json()

    assert len(knowledge_items) == 1
    assert knowledge_items[0]["title"] == "Company A Policy"
    assert knowledge_items[0]["company_id"] == company_a["id"]
