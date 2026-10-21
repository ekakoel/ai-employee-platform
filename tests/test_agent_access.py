"""Phase 3 — Human AI Access tests."""

import pytest
from fastapi import HTTPException
from app.services.access import require_agent_approve, require_agent_manage
from fastapi.testclient import TestClient

from tests.helpers import owner_setup, provision_company, bootstrap_demo, login_headers
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.services.seed import seed_catalog
from app.core.passwords import hash_password
from app.models.entities import (
    User,
    EmailClaim,
    Approval,
    ApprovalStatus,
    Task,
    TaskStatus,
)
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


def test_changing_supervisor_synchronizes_access_grants(client):
    (
        company_id,
        owner_id,
        owner_headers,
        member_id,
        member_headers,
        agent_id,
    ) = setup_company(client)

    # Ganti supervisor dari owner ke member.
    response = client.patch(
        f"/api/v1/companies/{company_id}/agents/{agent_id}",
        headers=owner_headers,
        json={"supervisor_user_id": member_id},
    )
    assert response.status_code == 200, response.text
    assert response.json()["supervisor_user_id"] == member_id

    # Pastikan hanya supervisor baru yang ditandai sebagai supervisor.
    response = client.get(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/access",
        headers=owner_headers,
    )
    assert response.status_code == 200, response.text

    grants = response.json()
    owner_grant = next(g for g in grants if g["user_id"] == owner_id)
    member_grant = next(g for g in grants if g["user_id"] == member_id)

    assert owner_grant["is_supervisor"] is False
    assert member_grant["is_supervisor"] is True


def test_clearing_supervisor_synchronizes_access_grants(client):
    (
        company_id,
        owner_id,
        owner_headers,
        member_id,
        member_headers,
        agent_id,
    ) = setup_company(client)

    # Hapus supervisor dengan mengirim null secara eksplisit.
    response = client.patch(
        f"/api/v1/companies/{company_id}/agents/{agent_id}",
        headers=owner_headers,
        json={"supervisor_user_id": None},
    )
    assert response.status_code == 200, response.text
    assert response.json()["supervisor_user_id"] is None

    response = client.get(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/access",
        headers=owner_headers,
    )
    assert response.status_code == 200, response.text

    grants = response.json()
    assert all(g["is_supervisor"] is False for g in grants)


def test_revoking_supervisor_access_clears_supervisor_reference(client):
    (
        company_id,
        owner_id,
        owner_headers,
        member_id,
        member_headers,
        agent_id,
    ) = setup_company(client)

    response = client.get(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/access",
        headers=owner_headers,
    )
    assert response.status_code == 200, response.text

    grants = response.json()
    owner_grant = next(g for g in grants if g["user_id"] == owner_id)
    access_id = owner_grant["id"]

    response = client.delete(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/access/{access_id}",
        headers=owner_headers,
    )
    assert response.status_code == 204, response.text

    # Referensi supervisor harus ikut dibersihkan.
    response = client.get(
        f"/api/v1/companies/{company_id}/agents",
        headers=owner_headers,
    )
    assert response.status_code == 200, response.text

    agent = next(a for a in response.json() if a["id"] == agent_id)
    assert agent["supervisor_user_id"] is None

    response = client.get(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/access",
        headers=owner_headers,
    )
    assert response.status_code == 200, response.text
    assert all(g["is_supervisor"] is False for g in response.json())



def test_inactive_user_cannot_be_assigned_as_supervisor(client):
    (
        company_id,
        owner_id,
        owner_headers,
        member_id,
        member_headers,
        agent_id,
    ) = setup_company(client)

    # Nonaktifkan member langsung pada database test.
    with SessionLocal() as db:
        member = db.get(User, member_id)
        assert member is not None
        member.status = "inactive"
        db.commit()

    # Owner mencoba menetapkan member nonaktif sebagai supervisor.
    response = client.patch(
        f"/api/v1/companies/{company_id}/agents/{agent_id}",
        headers=owner_headers,
        json={"supervisor_user_id": member_id},
    )

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == (
        "Supervisor must be an active user in this company"
    )

    # Supervisor awal harus tetap owner.
    response = client.get(
        f"/api/v1/companies/{company_id}/agents",
        headers=owner_headers,
    )
    assert response.status_code == 200, response.text

    agent = next(
        item for item in response.json()
        if item["id"] == agent_id
    )
    assert agent["supervisor_user_id"] == owner_id


def test_changing_supervisor_preserves_existing_permissions(client):
    (
        company_id,
        owner_id,
        owner_headers,
        member_id,
        member_headers,
        agent_id,
    ) = setup_company(client)

    # Berikan member seluruh permission sebelum menjadi supervisor.
    response = client.post(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/access",
        headers=owner_headers,
        json={
            "user_id": member_id,
            "can_use": True,
            "can_manage": True,
            "can_approve": True,
            "is_supervisor": False,
        },
    )
    assert response.status_code == 201, response.text

    # Jadikan member sebagai supervisor melalui endpoint konfigurasi agent.
    response = client.patch(
        f"/api/v1/companies/{company_id}/agents/{agent_id}",
        headers=owner_headers,
        json={"supervisor_user_id": member_id},
    )
    assert response.status_code == 200, response.text
    assert response.json()["supervisor_user_id"] == member_id

    # Pastikan permission tetap utuh dan hanya supervisor yang berubah.
    response = client.get(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/access",
        headers=owner_headers,
    )
    assert response.status_code == 200, response.text

    grants = response.json()
    owner_grant = next(g for g in grants if g["user_id"] == owner_id)
    member_grant = next(g for g in grants if g["user_id"] == member_id)

    assert owner_grant["is_supervisor"] is False

    assert member_grant["is_supervisor"] is True
    assert member_grant["can_use"] is True
    assert member_grant["can_manage"] is True
    assert member_grant["can_approve"] is True


def test_assigning_access_as_supervisor_sets_supervisor_flag(client):
    (
        company_id,
        owner_id,
        owner_headers,
        member_id,
        member_headers,
        agent_id,
    ) = setup_company(client)

    # Berikan akses sekaligus tetapkan member sebagai supervisor.
    response = client.post(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/access",
        headers=owner_headers,
        json={
            "user_id": member_id,
            "can_use": True,
            "can_manage": False,
            "can_approve": False,
            "is_supervisor": True,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["is_supervisor"] is True

    # Pastikan hanya member yang menjadi supervisor.
    response = client.get(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/access",
        headers=owner_headers,
    )
    assert response.status_code == 200, response.text

    grants = response.json()
    owner_grant = next(g for g in grants if g["user_id"] == owner_id)
    member_grant = next(g for g in grants if g["user_id"] == member_id)

    assert owner_grant["is_supervisor"] is False
    assert member_grant["is_supervisor"] is True


def test_updating_access_as_supervisor_sets_supervisor_flag(client):
    (
        company_id,
        owner_id,
        owner_headers,
        member_id,
        member_headers,
        agent_id,
    ) = setup_company(client)

    # Buat grant awal untuk member, tetapi jangan tetapkan sebagai supervisor.
    response = client.post(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/access",
        headers=owner_headers,
        json={
            "user_id": member_id,
            "can_use": True,
            "can_manage": True,
            "can_approve": True,
            "is_supervisor": False,
        },
    )
    assert response.status_code == 201, response.text
    access_id = response.json()["id"]

    # Ubah grant yang sama menjadi supervisor.
    response = client.patch(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/access/{access_id}",
        headers=owner_headers,
        json={"is_supervisor": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["is_supervisor"] is True

    # Pastikan permission sebelumnya tetap terjaga.
    assert response.json()["can_use"] is True
    assert response.json()["can_manage"] is True
    assert response.json()["can_approve"] is True

    response = client.get(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/access",
        headers=owner_headers,
    )
    assert response.status_code == 200, response.text

    grants = response.json()
    owner_grant = next(g for g in grants if g["user_id"] == owner_id)
    member_grant = next(g for g in grants if g["user_id"] == member_id)

    assert owner_grant["is_supervisor"] is False
    assert member_grant["is_supervisor"] is True

def test_member_without_can_approve_cannot_approve_or_reject(client):
    (
        company_id,
        owner_id,
        owner_headers,
        member_id,
        member_headers,
        agent_id,
    ) = setup_company(client)

    # Buat task sebagai owner.
    response = client.post(
        f"/api/v1/companies/{company_id}/tasks",
        headers=owner_headers,
        json={
            "agent_instance_id": agent_id,
            "title": "Approval authorization test",
            "instruction": "Test approval authorization",
        },
    )
    assert response.status_code == 201, response.text
    task_id = response.json()["id"]

    # Siapkan approval pending untuk task tersebut.
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        assert task is not None
        task.status = TaskStatus.WAITING_APPROVAL.value

        approval = Approval(
            company_id=company_id,
            task_id=task_id,
            agent_instance_id=agent_id,
            action="test_action",
            reason="Authorization regression test",
            payload={},
            status=ApprovalStatus.PENDING.value,
        )
        db.add(approval)
        db.commit()
        db.refresh(approval)
        approval_id = approval.id

    # Member tanpa can_approve tidak boleh menyetujui.
    response = client.post(
        f"/api/v1/companies/{company_id}/approvals/{approval_id}/approve",
        headers=member_headers,
        json={"comment": "Unauthorized approval attempt"},
    )
    assert response.status_code == 403, response.text

    # Member tanpa can_approve juga tidak boleh menolak.
    response = client.post(
        f"/api/v1/companies/{company_id}/approvals/{approval_id}/reject",
        headers=member_headers,
        json={"comment": "Unauthorized rejection attempt"},
    )
    assert response.status_code == 403, response.text

    # Kedua percobaan harus membiarkan approval tetap pending.
    with SessionLocal() as db:
        approval = db.get(Approval, approval_id)
        assert approval is not None
        assert approval.status == ApprovalStatus.PENDING.value
        assert approval.reviewed_by is None


def test_member_with_can_approve_can_approve_without_can_manage(
    client,
    monkeypatch,
):
    (
        company_id,
        owner_id,
        owner_headers,
        member_id,
        member_headers,
        agent_id,
    ) = setup_company(client)

    # Berikan hak penggunaan dan approval, tetapi bukan hak konfigurasi.
    response = client.post(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/access",
        headers=owner_headers,
        json={
            "user_id": member_id,
            "can_use": True,
            "can_manage": False,
            "can_approve": True,
            "is_supervisor": False,
        },
    )
    assert response.status_code == 201, response.text

    # Buat task sebagai owner.
    response = client.post(
        f"/api/v1/companies/{company_id}/tasks",
        headers=owner_headers,
        json={
            "agent_instance_id": agent_id,
            "title": "Authorized approval test",
            "instruction": "Test authorized approval",
        },
    )
    assert response.status_code == 201, response.text
    task_id = response.json()["id"]

    # Siapkan approval pending.
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        assert task is not None
        task.status = TaskStatus.WAITING_APPROVAL.value

        approval = Approval(
            company_id=company_id,
            task_id=task_id,
            agent_instance_id=agent_id,
            action="test_action",
            reason="Authorized approval regression test",
            payload={},
            status=ApprovalStatus.PENDING.value,
        )
        db.add(approval)
        db.commit()
        db.refresh(approval)
        approval_id = approval.id

    # Hindari menjalankan tool/runtime; pengujian ini hanya menguji otorisasi
    # dan transisi approval. Runtime punya pengujian tersendiri.
    def fake_resume_after_approval(
        self,
        db,
        *,
        company_id,
        task_id,
        approval_id,
    ):
        return db.get(Task, task_id)

    monkeypatch.setattr(
        "app.api.routes.TaskRuntimeService.resume_after_approval",
        fake_resume_after_approval,
    )

    response = client.post(
        f"/api/v1/companies/{company_id}/approvals/{approval_id}/approve",
        headers=member_headers,
        json={"comment": "Approved by authorized employee"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == ApprovalStatus.APPROVED.value
    assert response.json()["reviewed_by"] == member_id

    # Pastikan member tetap tidak memiliki hak konfigurasi agent.
    response = client.patch(
        f"/api/v1/companies/{company_id}/agents/{agent_id}",
        headers=member_headers,
        json={"name": "Unauthorized configuration"},
    )
    assert response.status_code == 403, response.text


def test_inactive_member_cannot_manage_or_approve_with_existing_grants(client):
    (
        company_id,
        owner_id,
        owner_headers,
        member_id,
        member_headers,
        agent_id,
    ) = setup_company(client)

    # Berikan kedua hak sebelum akun dinonaktifkan.
    response = client.post(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/access",
        headers=owner_headers,
        json={
            "user_id": member_id,
            "can_use": True,
            "can_manage": True,
            "can_approve": True,
            "is_supervisor": False,
        },
    )
    assert response.status_code == 201, response.text

    # Nonaktifkan akun, tetapi biarkan grant tetap ada.
    with SessionLocal() as db:
        member = db.get(User, member_id)
        assert member is not None
        member.status = "inactive"
        db.commit()

    # Kedua guard harus menolak akses walaupun grant masih aktif.
    with SessionLocal() as db:
        member = db.get(User, member_id)
        assert member is not None

        with pytest.raises(HTTPException) as manage_error:
            require_agent_manage(
                db,
                member,
                company_id=company_id,
                agent_instance_id=agent_id,
            )

        assert manage_error.value.status_code == 403
        assert manage_error.value.detail == (
            "User is not active in this company"
        )

        with pytest.raises(HTTPException) as approve_error:
            require_agent_approve(
                db,
                member,
                company_id=company_id,
                agent_instance_id=agent_id,
            )

        assert approve_error.value.status_code == 403
        assert approve_error.value.detail == (
            "User is not active in this company"
        )
