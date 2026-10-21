"""Phase 3 — Human AI Access tests."""

import pytest
from fastapi.testclient import TestClient

from tests.helpers import owner_setup, provision_company, bootstrap_demo, login_headers
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.services.seed import seed_catalog
from app.core.passwords import hash_password
from app.models.entities import User, EmailClaim
from app.services.seed import get_or_create_role

engine = create_engine(
    "sqlite:///./test_agent_access.db",
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


# def setup_company(client):
#     # auth-hardened: demo bootstrap instead of public company create
#     _cid, _oid, _hdrs, _demo = provision_company(client)
#     co = {"id": _cid}
#     owner = {"id": _oid, "email": _demo.get("owner_email")}
#     member = {"id": None}  # invite-only API; use bootstrap personas
#     catalog = client.get("/api/v1/agent-catalog").json()
#     res = next(i for i in catalog if i["slug"] == "reservation")
#     hire = client.post(
#         f"/api/v1/companies/{co['id']}/agents/{res['id']}/hire",
#         json={"name": "Desk AI"},
#         headers=_hdrs,
#     )
#     assert hire.status_code == 201, hire.text
#     return co["id"], owner["id"], member["id"], hire.json()["id"]

def setup_company(client):
    # Siapkan company dan autentikasi owner.
    company_id, owner_id, owner_headers, demo = provision_company(client)

    catalog = client.get("/api/v1/agent-catalog").json()
    reservation = next(
        item for item in catalog if item["slug"] == "reservation"
    )

    hire = client.post(
        f"/api/v1/companies/{company_id}/agents/{reservation['id']}/hire",
        json={"name": "Desk AI"},
        headers=owner_headers,
    )
    assert hire.status_code == 201, hire.text

    
    # Buat member setelah agen di-hire agar setup test ini
    # tidak memberikan grant akses operasional secara otomatis.
    member_email = f"member-{owner_id}@test.local"

    with SessionLocal() as db:
        role = get_or_create_role(db, "member")

        if db.get(EmailClaim, member_email) is None:
            db.add(EmailClaim(email=member_email))
            db.flush()

        member = User(
            company_id=company_id,
            name="Test Member",
            email=member_email,
            role_id=role.id,
            password_hash=hash_password("test-password-123"),
            email_verified=True,
            status="active",
        )
        db.add(member)
        db.commit()
        db.refresh(member)
        member_id = member.id

    member_headers = login_headers(
        client,
        member_email,
        password="test-password-123",
    )

    return (
        company_id,
        owner_id,
        owner_headers,
        member_id,
        member_headers,
        hire.json()["id"],
    )




def test_hire_auto_grants_supervisor_access(client):
    company_id, owner_id, owner_headers, member_id, member_headers, agent_id = (
        setup_company(client)
    )
    access = client.get(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/access",
        headers=owner_headers,
    )
    assert access.status_code == 200
    grants = access.json()

    owner_grant = next(
        (grant for grant in grants if grant["user_id"] == owner_id),
        None,
    )

    assert owner_grant is not None
    assert owner_grant["can_use"] is True
    assert owner_grant["can_manage"] is True
    assert owner_grant["can_approve"] is True
    assert owner_grant["is_supervisor"] is True

    inst = client.get(
        f"/api/v1/companies/{company_id}/agents",
        headers=owner_headers,
    ).json()
    row = next(i for i in inst if i["id"] == agent_id)
    assert row["supervisor_user_id"] == owner_id


def test_member_without_access_cannot_create_task(client):
    company_id, owner_id, owner_headers, member_id, member_headers, agent_id = (
        setup_company(client)
    )
    resp = client.post(
        f"/api/v1/companies/{company_id}/tasks",
        headers=member_headers,
        json={
            "agent_instance_id": agent_id,
            "title": "Hello",
            "instruction": "Do something",
        },
    )
    assert resp.status_code == 403


def test_member_with_use_access_can_create_task(client):
    company_id, owner_id, owner_headers, member_id, member_headers, agent_id = (
        setup_company(client)
    )
    assign = client.post(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/access",
        headers=owner_headers,
        json={
            "user_id": member_id,
            "can_use": True,
            "can_manage": False,
            "can_approve": False,
        },
    )
    assert assign.status_code == 201, assign.text

    resp = client.post(
        f"/api/v1/companies/{company_id}/tasks",
        headers=member_headers,
        json={
            "agent_instance_id": agent_id,
            "title": "Hello",
            "instruction": "Do something",
        },
    )
    assert resp.status_code == 201, resp.text


def test_member_cannot_configure_without_manage(client):
    company_id, owner_id, owner_headers, member_id, member_headers, agent_id = (
        setup_company(client)
    )
    client.post(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/access",
        headers=owner_headers,
        json={"user_id": member_id, "can_use": True, "can_manage": False},
    )
    resp = client.patch(
        f"/api/v1/companies/{company_id}/agents/{agent_id}",
        headers=member_headers,
        json={"instructions": "hacked"},
    )
    assert resp.status_code == 403


def test_member_with_manage_can_configure(client):
    company_id, owner_id, owner_headers, member_id, member_headers, agent_id = (
        setup_company(client)
    )
    client.post(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/access",
        headers=owner_headers,
        json={"user_id": member_id, "can_use": True, "can_manage": True},
    )
    resp = client.patch(
        f"/api/v1/companies/{company_id}/agents/{agent_id}",
        headers=member_headers,
        json={"instructions": "Company custom instructions"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["instructions"] == "Company custom instructions"
