from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.services.seed import seed_catalog


engine = create_engine("sqlite:///./test_ai_employee.db", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base.metadata.create_all(bind=engine)
with TestingSessionLocal() as db:
    seed_catalog(db)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_company_hires_agent_and_can_create_task():
    company = client.post("/api/v1/companies", json={"name": "Bali Kami Test"})
    assert company.status_code == 201
    company_id = company.json()["id"]

    catalog = client.get("/api/v1/agent-catalog").json()
    reservation = next(x for x in catalog if x["slug"] == "reservation")

    hired = client.post(
        f"/api/v1/companies/{company_id}/agents/{reservation['id']}/hire",
        json={"name": "Reservation Agent Bali Kami"},
    )
    assert hired.status_code == 201
    agent_id = hired.json()["id"]

    task = client.post(
        f"/api/v1/companies/{company_id}/tasks",
        json={"agent_instance_id": agent_id, "title": "Check booking", "instruction": "Check availability"},
    )
    assert task.status_code == 201


def test_company_cannot_create_task_with_other_company_agent():
    company_a = client.post("/api/v1/companies", json={"name": "Company A"}).json()
    company_b = client.post("/api/v1/companies", json={"name": "Company B"}).json()
    reservation = next(x for x in client.get("/api/v1/agent-catalog").json() if x["slug"] == "reservation")

    hired = client.post(
        f"/api/v1/companies/{company_b['id']}/agents/{reservation['id']}/hire",
        json={"name": "Company B Reservation"},
    ).json()

    response = client.post(
        f"/api/v1/companies/{company_a['id']}/tasks",
        json={"agent_instance_id": hired["id"], "title": "Forbidden", "instruction": "Should fail"},
    )
    assert response.status_code == 403
