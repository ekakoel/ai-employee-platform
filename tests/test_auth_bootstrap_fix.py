
"""Regression tests for authenticated bootstrap and employee creation."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import (
    admin_routes,
    auth_routes,
    company_onboarding_routes,
    inbox_routes,
    result_routes,
    routes,
)
from app.core.database import Base, get_db
from app.main import app as production_app
from app.services.seed import seed_catalog
from tests.helpers import provision_company


@pytest.fixture()
def client():
    """Use an isolated app and in-memory SQLite without production lifespan."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    test_app = FastAPI()

    for api_router in (
        auth_routes.router,
        company_onboarding_routes.router,
        admin_routes.router,
        routes.router,
        result_routes.router,
        inbox_routes.router,
    ):
        test_app.include_router(api_router)

    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        seed_catalog(db)

    def override_get_db():
        with SessionLocal() as db:
            yield db

    test_app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(test_app) as test_client:
            yield test_client
    finally:
        test_app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_first_user_with_stale_x_user_header(client):
    """A stale X-User-ID must not override a valid Bearer identity."""
    company_id, owner_id, headers, _demo = provision_company(client)

    response = client.get(
        "/api/v1/auth/me",
        headers={
            **headers,
            "X-User-ID": "00000000-0000-0000-0000-000000000000",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["user_id"] == owner_id
    assert response.json()["company_id"] == company_id


def test_second_user_requires_auth(client):
    """Employee creation requires authentication and uses invitations."""
    company_id, _owner_id, headers, _demo = provision_company(client)

    payload = {
        "name": "Member",
        "email": "m1@two.test",
        "role": "member",
    }

    anonymous = client.post(
        f"/api/v1/companies/{company_id}/users",
        json=payload,
    )

    assert anonymous.status_code == 401, anonymous.text

    authenticated = client.post(
        f"/api/v1/companies/{company_id}/users",
        headers=headers,
        json=payload,
    )

    assert authenticated.status_code == 410, authenticated.text
    assert "invitations" in authenticated.json()["detail"].lower()


def test_workspace_has_clear_session():
    """Check the production workspace page without starting its lifespan."""
    response = TestClient(production_app).get("/workspace")

    assert response.status_code == 200
    assert b"btnClearSession" in response.content
    assert b"btnQuickStart" in response.content
