
"""Regression: first user bootstrap must work even with stale auth headers."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.services.seed import seed_catalog
from tests.helpers import provision_company


@pytest.fixture()
def client(tmp_path):
    # Use a disposable database outside the project workspace.
    database_path = (tmp_path / "auth_bootstrap.sqlite3").resolve()
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        seed_catalog(db)

    def override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override

        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_first_user_with_stale_x_user_header(client):
    # Use the supported demo bootstrap flow.
    company_id, _owner_id, _headers, _demo = provision_company(client)

    # A stale user ID must not prevent the first user from being created.
    user = client.post(
        f"/api/v1/companies/{company_id}/users",
        headers={
            "X-User-ID": "00000000-0000-0000-0000-000000000000"
        },
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
            "company_id": company_id,
            "email": "owner@fresh.test",
            "password": "secret123",
        },
    )

    assert login.status_code == 200, login.text


def test_second_user_requires_auth(client):
    # Bootstrap the company and its initial owner.
    company_id, _owner_id, _headers, _demo = provision_company(client)

    # The first user can be created through the bootstrap flow.
    first = client.post(
        f"/api/v1/companies/{company_id}/users",
        json={
            "name": "Owner",
            "email": "o1@two.test",
            "role": "owner",
            "password": "secret123",
        },
    )

    assert first.status_code == 201, first.text

    # An unauthenticated request must not create a second user.
    second = client.post(
        f"/api/v1/companies/{company_id}/users",
        json={
            "name": "Member",
            "email": "m1@two.test",
            "role": "member",
        },
    )

    assert second.status_code == 401, second.text


def test_workspace_has_clear_session():
    html = TestClient(app).get("/workspace").content

    assert b"btnClearSession" in html
    assert b"btnQuickStart" in html
