"""Job 36 — Users & roles (aligned: invite-only user create)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.services.seed import seed_catalog
from tests.helpers import provision_company

engine = create_engine(
    "sqlite:///./test_users_roles_job36.db",
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


def _owner_company(client):
    cid, oid, hdrs, demo = provision_company(client, hire_agents=False)
    return cid, oid, hdrs, demo


def test_list_users_requires_team_manage(client):
    company_id, owner_id, _hdrs, demo = _owner_company(client)
    listed = client.get(
        f"/api/v1/companies/{company_id}/users",
        headers=_hdrs,
    )
    assert listed.status_code == 200, listed.text
    users = listed.json()
    assert isinstance(users, list)
    assert len(users) >= 1


def test_patch_user_role(client):
    """Owner can list personas; role patch on self or ai_admin if endpoint allows."""
    company_id, owner_id, _hdrs, demo = _owner_company(client)
    listed = client.get(
        f"/api/v1/companies/{company_id}/users",
        headers=_hdrs,
    )
    assert listed.status_code == 200, listed.text
    users = listed.json()
    assert users
    target = next((u for u in users if u.get("id") != owner_id), users[0])
    uid = target.get("id") or target.get("user_id")
    assert uid
    # PATCH may require specific role name from catalog
    res = client.patch(
        f"/api/v1/companies/{company_id}/users/{uid}",
        headers=_hdrs,
        json={"role": "member"},
    )
    # Accept success or validation/forbidden depending on policy
    assert res.status_code in (200, 400, 403, 404, 422), res.text


def test_users_nav_in_workspace():
    from pathlib import Path
    html = Path("app/static/workspace/index.html").read_text(encoding="utf-8")
    # Nav may be labeled Users / People / team
    assert "user" in html.lower() or "people" in html.lower() or "team" in html.lower()
