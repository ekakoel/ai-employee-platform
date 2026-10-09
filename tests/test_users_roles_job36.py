"""Job 36 — list/update company users, role name on UserRead."""

import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _owner_company():
    suffix = uuid.uuid4().hex[:8]
    co = client.post("/api/v1/companies", json={"name": f"Co36 {suffix}"}).json()
    owner = client.post(
        f"/api/v1/companies/{co["id"]}/users",
        json={
            "name": "Owner",
            "email": f"owner-{suffix}@job36.test",
            "role": "owner",
            "password": "demo12345",
        },
    ).json()
    return co["id"], owner["id"]


def test_list_users_requires_team_manage():
    company_id, owner_id = _owner_company()
    res = client.post(
        f"/api/v1/companies/{company_id}/users",
        headers={"X-User-ID": owner_id},
        json={
            "name": "Res",
            "email": f"res-{uuid.uuid4().hex[:6]}@job36.test",
            "role": "reservation",
            "password": "demo12345",
        },
    )
    assert res.status_code in (200, 201), res.text
    res_id = res.json()["id"]
    assert res.json().get("role") == "reservation"

    denied = client.get(
        f"/api/v1/companies/{company_id}/users",
        headers={"X-User-ID": res_id},
    )
    assert denied.status_code == 403

    ok = client.get(
        f"/api/v1/companies/{company_id}/users",
        headers={"X-User-ID": owner_id},
    )
    assert ok.status_code == 200, ok.text
    assert len(ok.json()) >= 2
    assert any(u.get("role") == "owner" for u in ok.json())


def test_patch_user_role():
    company_id, owner_id = _owner_company()
    member = client.post(
        f"/api/v1/companies/{company_id}/users",
        headers={"X-User-ID": owner_id},
        json={
            "name": "Member",
            "email": f"mem-{uuid.uuid4().hex[:6]}@job36.test",
            "role": "member",
            "password": "demo12345",
        },
    ).json()
    patched = client.patch(
        f"/api/v1/companies/{company_id}/users/{member["id"]}",
        headers={"X-User-ID": owner_id},
        json={"role": "ai_admin"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["role"] == "ai_admin"


def test_users_nav_in_workspace():
    html = client.get("/workspace").content
    assert b'data-view="users"' in html
    assert b"view-users" in html
