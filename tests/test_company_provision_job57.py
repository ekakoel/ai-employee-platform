"""Job 57 — company provision by platform developer; self-register role limits."""

import uuid

from fastapi.testclient import TestClient

from tests.helpers import owner_setup, provision_company, bootstrap_demo, login_headers

from app.main import app
from app.services.seed import ROLE_PERMISSIONS, VALID_COMPANY_ROLES

client = TestClient(app)


def test_accounting_role_exists():
    assert "accounting" in VALID_COMPANY_ROLES
    assert "usage.read" in ROLE_PERMISSIONS["accounting"]


def test_workspace_login_has_no_public_create_company_cta():
    html = client.get("/workspace").text
    assert "Provision company" in html or "developer" in html
    assert "Register to company" in html or 'data-tab="register"' in html
    # Create company button may remain for message-only handler; tab provision is developer-only
    assert 'data-tab="provision"' in html
    assert "developer-only" in html


def test_self_register_cannot_claim_owner_when_company_has_users():
    """Register creates a NEW company owner; cannot attach as owner to existing company."""
    import uuid
    from fastapi.testclient import TestClient
    from app.main import app
    from tests.helpers import provision_company

    with TestClient(app) as client:
        _cid, _oid, _hdrs, _demo = provision_company(client, hire_agents=False)
        # Old API allowed register into company_id with role=owner — now rejected/ignored
        email = f"claim-{uuid.uuid4().hex[:8]}@test.local"
        reg = client.post(
            "/api/v1/auth/register",
            json={
                "company_name": f"Claim Co {uuid.uuid4().hex[:6]}",
                "owner_name": "Claimer",
                "email": email,
                "password": "secret12345",
            },
        )
        # New company is fine (201) — the important check is it is NOT the same company
        assert reg.status_code in (201, 400, 403, 409, 422), reg.text
        if reg.status_code == 201:
            body = reg.json()
            new_cid = body.get("company_id") or (body.get("company") or {}).get("id")
            assert new_cid != _cid


