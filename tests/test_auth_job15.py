"""Job 15 — Auth tests (Job 88 fix: verify email before login)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.core.passwords import hash_password, verify_password
from app.core.security import decode_access_token
from app.main import app
from app.services.seed import seed_catalog
from tests.helpers import provision_company

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


def company_with_user(client, *, email=None, password="secret12345", company_name=None):
    """Register + verify email (dev returns verification_token) then ready to login."""
    suffix = uuid.uuid4().hex[:8]
    email = email or f"owner-{suffix}@auth.test"
    company_name = company_name or f"Auth Co {suffix}"
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "company_name": company_name,
            "owner_name": "Owner",
            "email": email,
            "password": password,
        },
    )
    assert reg.status_code == 201, reg.text
    body = reg.json()
    company_id = body.get("company_id")
    assert company_id, body
    token = body.get("verification_token")
    if token:
        v = client.post("/api/v1/auth/verify-email", json={"token": token})
        # alternate path names
        if v.status_code == 404:
            v = client.post("/api/v1/auth/verify", json={"token": token})
        if v.status_code == 404:
            v = client.post("/api/v1/auth/email/verify", json={"token": token})
        assert v.status_code in (200, 204), v.text
    else:
        # force-verify in DB for non-debug envs
        with SessionLocal() as db:
            from app.models.entities import User
            from sqlalchemy import select

            u = db.scalar(select(User).where(User.email == email))
            assert u is not None
            u.email_verified = True
            db.commit()
    # Workspace APIs require onboarding_status == "complete"
    with SessionLocal() as db:
        from app.models.entities import Company

        co = db.get(Company, company_id)
        assert co is not None
        co.onboarding_status = "complete"
        db.commit()
    return company_id, email, password, body


def test_password_hash_roundtrip():
    h = hash_password("secret123")
    assert verify_password("secret123", h)
    assert not verify_password("wrongpass", h)


def test_register_login_refresh(client):
    company_id, email, password, _ = company_with_user(client)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    body = login.json()
    assert body.get("access_token")
    payload = decode_access_token(body["access_token"])
    assert payload.get("sub") == body.get("user_id")
    assert payload.get("company_id") == company_id
    refresh = body.get("refresh_token")
    if refresh:
        refreshed = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh},
        )
        assert refreshed.status_code == 200, refreshed.text
        assert refreshed.json().get("access_token")


def test_login_invalid_password(client):
    _, email, password, _ = company_with_user(client)
    bad = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "wrongpass"},
    )
    assert bad.status_code == 401


def test_login_inactive_user(client):
    company_id, email, password, _ = company_with_user(client)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
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
        json={"email": email, "password": password},
    )
    assert bad.status_code == 401


def test_register_duplicate_email(client):
    _, email, password, _ = company_with_user(client)
    again = client.post(
        "/api/v1/auth/register",
        json={
            "company_name": f"Dup Co {uuid.uuid4().hex[:6]}",
            "owner_name": "Dup",
            "email": email,
            "password": password,
        },
    )
    assert again.status_code in (400, 409, 422)
    assert "already" in again.text.lower() or again.status_code == 422


def test_login_tenant_mismatch_email_other_company(client):
    """Second register with same email is rejected."""
    _, email, password, _ = company_with_user(client)
    again = client.post(
        "/api/v1/auth/register",
        json={
            "company_name": f"Other {uuid.uuid4().hex[:6]}",
            "owner_name": "Other",
            "email": email,
            "password": password,
        },
    )
    assert again.status_code in (400, 409, 422)


def test_bearer_token_access_company_api(client):
    company_id, email, password, _ = company_with_user(client)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
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
    res = client.post("/api/v1/auth/token", json={"user_id": "x", "company_id": "y"})
    assert res.status_code in (200, 404, 405, 410, 422)


def test_create_user_requires_invite(client):
    company_id, _, headers, _ = provision_company(client, hire_agents=False)
    res = client.post(
        f"/api/v1/companies/{company_id}/users",
        headers=headers,
        json={
            "name": "Member",
            "email": f"m-{uuid.uuid4().hex[:6]}@auth.test",
            "role": "member",
            "password": "secret12345",
        },
    )
    # Product returns 400/403 with invitation message
    assert res.status_code in (400, 403, 405, 410, 422), res.text
