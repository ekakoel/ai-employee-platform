"""Job 35 — company roles, /me, permission matrix, workspace gating hooks."""

import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.services.seed import ROLE_PERMISSIONS, VALID_COMPANY_ROLES

client = TestClient(app)


def _company_with_user(role: str, email: str):
    suffix = uuid.uuid4().hex[:8]
    co_res = client.post(
        "/api/v1/companies",
        json={"name": f"Co {role} {suffix}"},
    )
    assert co_res.status_code in (200, 201), co_res.text
    co = co_res.json()
    assert "id" in co, co

    user = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={
            "name": f"User {role}",
            "email": email,
            "role": role,
            "password": "demo12345",
        },
    )
    assert user.status_code in (200, 201), user.text
    return co["id"], user.json()


def test_seed_roles_include_ai_admin_and_reservation():
    assert "ai_admin" in VALID_COMPANY_ROLES
    assert "reservation" in VALID_COMPANY_ROLES
    assert "agent.manage" in ROLE_PERMISSIONS["ai_admin"]
    assert "team.manage" not in ROLE_PERMISSIONS["ai_admin"]
    assert "task.create" in ROLE_PERMISSIONS["reservation"]
    assert "agent.manage" not in ROLE_PERMISSIONS["reservation"]
    assert "team.manage" in ROLE_PERMISSIONS["owner"]


def test_me_returns_role_and_permissions():
    email = f"res-{uuid.uuid4().hex[:8]}@job35.test"
    company_id, user = _company_with_user("reservation", email)
    tok = client.post(
        "/api/v1/auth/login",
        json={
            "company_id": company_id,
            "email": email,
            "password": "demo12345",
        },
    )
    assert tok.status_code == 200, tok.text
    body = tok.json()
    assert body.get("role") == "reservation"
    assert "task.create" in body.get("permissions", [])
    assert "agent.manage" not in body.get("permissions", [])

    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200, me.text
    data = me.json()
    assert data["role"] == "reservation"
    assert data["user_id"] == body["user_id"]
    assert "task.read" in data["permissions"]
    assert data["company_id"] == company_id


def test_reservation_cannot_team_manage_route():
    email = f"res2-{uuid.uuid4().hex[:8]}@job35.test"
    company_id, user = _company_with_user("reservation", email)
    uid = user["id"]
    catalog = client.get("/api/v1/agent-catalog").json()
    assert catalog
    hire = client.post(
        f"/api/v1/companies/{company_id}/agents/{catalog[0]['id']}/hire",
        headers={"X-User-ID": uid},
        json={"name": "Should Fail"},
    )
    assert hire.status_code == 403, hire.text


def test_ai_admin_can_hire():
    email = f"admin-{uuid.uuid4().hex[:8]}@job35.test"
    company_id, user = _company_with_user("ai_admin", email)
    catalog = client.get("/api/v1/agent-catalog").json()
    hire = client.post(
        f"/api/v1/companies/{company_id}/agents/{catalog[0]['id']}/hire",
        headers={"X-User-ID": user["id"]},
        json={"name": "AI Admin Hire"},
    )
    assert hire.status_code in (200, 201), hire.text


def test_workspace_and_developer_pages():
    ws = client.get("/workspace")
    assert ws.status_code == 200
    assert b"chatModeNotice" in ws.content or b"advisory" in ws.content.lower()
    assert b'data-workspace="user"' in ws.content

    dev = client.get("/developer")
    assert dev.status_code == 200
    assert b'data-workspace="developer"' in dev.content

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json().get("developer") == "/developer"


def test_me_requires_auth():
    res = client.get("/api/v1/auth/me")
    assert res.status_code == 401
