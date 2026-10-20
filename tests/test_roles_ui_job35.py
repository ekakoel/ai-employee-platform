"""Job 35 — company roles, /me, permission matrix, workspace gating hooks."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.seed import ROLE_PERMISSIONS, VALID_COMPANY_ROLES
from tests.helpers import provision_company, login_headers, DEMO_PASSWORD

client = TestClient(app)


def test_role_matrix_has_expected_roles():
    assert "owner" in VALID_COMPANY_ROLES
    assert "ai_admin" in VALID_COMPANY_ROLES
    assert "reservation" in VALID_COMPANY_ROLES
    assert "agent.hire" in ROLE_PERMISSIONS["owner"]
    assert "agent.hire" in ROLE_PERMISSIONS["ai_admin"]
    assert "team.manage" in ROLE_PERMISSIONS["owner"]


def test_reservation_cannot_hire():
    company_id, uid, headers, demo = provision_company(client, role="reservation")
    catalog = client.get("/api/v1/agent-catalog", headers=headers).json()
    assert catalog
    hire = client.post(
        f"/api/v1/companies/{company_id}/agents/{catalog[0]['id']}/hire",
        headers=headers,
        json={"name": "Should Fail"},
    )
    assert hire.status_code == 403, hire.text


def test_ai_admin_can_hire():
    company_id, uid, headers, demo = provision_company(client, role="ai_admin")
    catalog = client.get("/api/v1/agent-catalog", headers=headers).json()
    assert catalog
    hire = client.post(
        f"/api/v1/companies/{company_id}/agents/{catalog[0]['id']}/hire",
        headers=headers,
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


def test_me_with_owner_token():
    company_id, uid, headers, demo = provision_company(client, role="owner")
    res = client.get("/api/v1/auth/me", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("company_id") == company_id
    assert body.get("role") in ("owner", None) or "owner" in str(body)
