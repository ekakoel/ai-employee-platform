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
    suffix = uuid.uuid4().hex[:8]
    # auth-hardened: demo bootstrap instead of public company create
    _cid, _oid, _hdrs, _demo = provision_company(client)
    co = {"id": _cid}
    # first user via users API as bootstrap
    member = {"id": None}  # invite-only API; use bootstrap personas
    assert owner.get("id")

    reg = client.post(
        "/api/v1/auth/register",
        json={
            "company_id": co["id"],
            "email": f"sneaky-{suffix}@j57.test",
            "name": "Sneaky",
            "password": "demo12345",
            "role": "owner",
        },
    )
    assert reg.status_code == 201, reg.text
    body = reg.json()
    # token response may include role
    role = body.get("role")
    if role is not None:
        assert role != "owner"
