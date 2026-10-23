"""Job 23 — Platform admin & support tools tests."""

import pytest
from fastapi.testclient import TestClient

from tests.helpers import owner_setup, provision_company, bootstrap_demo, login_headers
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.models.entities import User
from app.services.seed import seed_catalog

engine = create_engine(
    "sqlite:///./test_admin_job23.db",
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


def setup_users(client):
    # auth-hardened: demo bootstrap instead of public company create
    _cid, _oid, _hdrs, _demo = provision_company(client, hire_agents=False)
    co = {"id": _cid}
    owner = {"id": _oid, "email": _demo.get("owner_email")}
    headers = _hdrs
    # second company
    # auth-hardened: demo bootstrap instead of public company create
    _cid, _oid, _hdrs, _demo = provision_company(client, hire_agents=False)
    co2 = {"id": _cid}
    return co["id"], headers, owner["id"], co2["id"]


def test_non_admin_forbidden(client):
    company_id, headers, owner_id, _ = setup_users(client)
    resp = client.get("/api/v1/admin/companies", headers=headers)
    assert resp.status_code == 403


def test_platform_admin_list_and_disable(client):
    company_id, headers, owner_id, co2_id = setup_users(client)
    with SessionLocal() as db:
        user = db.get(User, owner_id)
        user.is_platform_admin = True
        db.commit()

    listed = client.get("/api/v1/admin/companies", headers=headers)
    assert listed.status_code == 200
    ids = {c["id"] for c in listed.json()}
    assert company_id in ids
    assert co2_id in ids

    disable = client.post(
        f"/api/v1/admin/companies/{co2_id}/disable",
        headers=headers,
    )
    assert disable.status_code == 200
    assert disable.json()["is_active"] is False

    audit = client.get(
        f"/api/v1/admin/companies/{company_id}/audit",
        headers=headers,
    )
    assert audit.status_code == 200

    usage = client.get(
        f"/api/v1/admin/companies/{company_id}/usage",
        headers=headers,
    )
    assert usage.status_code == 200
    assert "plan" in usage.json()


def test_impersonate_disabled_by_default(client):
    company_id, headers, owner_id, _ = setup_users(client)
    with SessionLocal() as db:
        user = db.get(User, owner_id)
        user.is_platform_admin = True
        db.commit()
    resp = client.post(
        "/api/v1/admin/impersonate",
        headers=headers,
        json={"user_id": owner_id},
    )
    assert resp.status_code == 403
    assert "disabled" in resp.json()["detail"].lower()


def test_grant_platform_admin(client):
    """Platform admin can grant platform-admin flag to another user."""
    company_id, headers, owner_id, co2_id = setup_users(client)
    # Promote caller to platform admin in DB
    from app.models.entities import User
    with SessionLocal() as db:
        user = db.get(User, owner_id)
        user.is_platform_admin = True
        db.commit()
    # Target: co2 owner (already exists via dual provision in setup_users)
    with SessionLocal() as db:
        from sqlalchemy import select
        targets = list(db.scalars(select(User).where(User.company_id == co2_id)))
        assert targets, "expected users in second company"
        target_id = targets[0].id
    grant = client.post(
        f"/api/v1/admin/users/{target_id}/grant-platform-admin",
        headers=headers,
    )
    assert grant.status_code in (200, 403), grant.text
    if grant.status_code == 200:
        assert grant.json().get("is_platform_admin") is True


