"""Regression: first user bootstrap must work even with stale auth headers."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.services.seed import seed_catalog

engine = create_engine(
    "sqlite:///./test_auth_bootstrap.db",
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


def test_first_user_with_stale_x_user_header(client):
    co = client.post("/api/v1/companies", json={"name": "Fresh Co"}).json()
    # Stale user id from another session must not block first user
    user = client.post(
        f"/api/v1/companies/{co['id']}/users",
        headers={"X-User-ID": "00000000-0000-0000-0000-000000000000"},
        json={
            "name": "Owner",
            "email": "owner@fresh.test",
            "role": "owner",
            "password": "secret123",
        },
    )
    assert user.status_code == 201, user.text
    assert user.json()["email"] == "owner@fresh.test"

    login = client.post(
        "/api/v1/auth/login",
        json={
            "company_id": co["id"],
            "email": "owner@fresh.test",
            "password": "secret123",
        },
    )
    assert login.status_code == 200


def test_second_user_requires_auth(client):
    co = client.post("/api/v1/companies", json={"name": "Two User Co"}).json()
    first = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={
            "name": "Owner",
            "email": "o1@two.test",
            "role": "owner",
            "password": "secret123",
        },
    )
    assert first.status_code == 201
    second = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={
            "name": "Member",
            "email": "m1@two.test",
            "role": "member",
        },
    )
    assert second.status_code == 401


def test_workspace_has_clear_session():
    html = TestClient(app).get("/workspace").content
    assert b"btnClearSession" in html
    assert b"btnQuickStart" in html
