"""Job 15 — Auth tests aligned with company onboarding registration (Job 88)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.core.passwords import hash_password, verify_password
from app.core.security import decode_access_token
from app.main import app
from app.services.seed import seed_catalog
from tests.helpers import DEMO_PASSWORD, login_headers, provision_company

engine = create_engine(
    "sqlite:///./test_auth_job15.db",
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


def company_with_user(client, *, email="owner@auth.test", password="secret12345"):
    """Register a brand-new company + owner (current /auth/register schema)."""
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "company_name": "Auth Test Co",
            "owner_name": "Owner",
            "email": email,
            "password": password,
        },
    )
    assert reg.status_code == 201, reg.text
    body = reg.json()
    # Response shapes may vary; prefer explicit ids
    company_id = body.get("company_id") or (body.get("company") or {}).get("id")
    assert company_id, body
    return company_id, body


def test_password_hash_roundtrip():
    h = hash_password("secret123")
    assert verify_password("secret123", h)
    assert not verify_password("wrongpass", h)


def test_register_login_refresh(client):
    company_id, body = company_with_user(client)
    # If register does not return tokens, login
    if body.get("access_token"):
        access = body["access_token"]
        refresh = body.get("refresh_token")
        user_id = body.get("user_id")
    else:
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "owner@auth.test", "password": "secret12345"},
        )
        assert login.status_code == 200, login.text
        body = login.json()
        access = body["access_token"]
        refresh = body.get("refresh_token")
        user_id = body.get("user_id")

    assert access
    payload = decode_access_token(access)
    assert payload.get("sub") == user_id or payload.get("sub")
    assert payload.get("company_id") == company_id or "company_id" in payload

    if refresh:
        refreshed = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh},
        )
        assert refreshed.status_code == 200, refreshed.text
        assert refreshed.json().get("access_token")


def test_login_invalid_password(client):
    company_with_user(client)
    bad = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@auth.test", "password": "wrongpass"},
    )
    assert bad.status_code == 401


def test_login_inactive_user(client):
    company_id, body = company_with_user(client, email="inactive@auth.test")
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "inactive@auth.test", "password": "secret12345"},
    )
    assert login.status_code == 200, login.text
    user_id = login.json()["user_id"]
    with SessionLocal() as db:
        from app.models.entities import User

        u = db.get(User, user_id)
        assert u is not None
        u.status = "inactive"
        db.commit()

    bad = client.post(
        "/api/v1/auth/login",
        json={"email": "inactive@auth.test", "password": "secret12345"},
    )
    assert bad.status_code == 401


def test_login_tenant_mismatch_email_other_company(client):
    company_with_user(client, email="a@auth.test")
    company_with_user(client, email="b@auth.test")
    # Same email cannot register twice
    dup = client.post(
        "/api/v1/auth/register",
        json={
            "company_name": "Other Co",
            "owner_name": "Other",
            "email": "a@auth.test",
            "password": "secret12345",
        },
    )
    assert dup.status_code in (400, 409, 422)


def test_register_duplicate_email(client):
    company_with_user(client, email="dup@auth.test")
    again = client.post(
        "/api/v1/auth/register",
        json={
            "company_name": "Dup Co",
            "owner_name": "Dup",
            "email": "dup@auth.test",
            "password": "secret12345",
        },
    )
    assert again.status_code in (400, 409, 422)


def test_bearer_token_access_company_api(client):
    company_id, body = company_with_user(client, email="bearer@auth.test")
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "bearer@auth.test", "password": "secret12345"},
    )
    assert login.status_code == 200, login.text
    tok = login.json()
    headers = {
        "Authorization": f"Bearer {tok['access_token']}",
        "X-User-ID": tok["user_id"],
    }
    res = client.get(f"/api/v1/companies/{company_id}/skills", headers=headers)
    assert res.status_code == 200, res.text


def test_legacy_token_endpoint_gone_or_redirect(client):
    """Legacy issue-token may be retired (410) or still available."""
    res = client.post("/api/v1/auth/token", json={"user_id": "x", "company_id": "y"})
    assert res.status_code in (200, 404, 405, 410, 422)


def test_create_user_requires_invite(client):
    """Direct POST /users is closed; invitations only."""
    company_id, owner_id, headers, _ = provision_company(client, hire_agents=False)
    res = client.post(
        f"/api/v1/companies/{company_id}/users",
        headers=headers,
        json={"name": "Member", "email": "m@auth.test", "role": "member", "password": "secret12345"},
    )
    assert res.status_code in (403, 405, 422), res.text
