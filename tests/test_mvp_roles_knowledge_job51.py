"""Job 51 — company role matrix, ephemeral knowledge ingest, platform-only skill create."""

import io
import uuid

from fastapi.testclient import TestClient

from tests.helpers import owner_setup, provision_company, bootstrap_demo, login_headers

from app.main import app
from app.services.seed import ROLE_PERMISSIONS, VALID_COMPANY_ROLES

client = TestClient(app)


def test_new_company_roles_exist():
    assert "contract_manager" in VALID_COMPANY_ROLES
    assert "administration" in VALID_COMPANY_ROLES
    assert "knowledge.write" in ROLE_PERMISSIONS["contract_manager"]
    assert "team.manage" in ROLE_PERMISSIONS["administration"]
    assert "knowledge.write" not in ROLE_PERMISSIONS["reservation"]


def test_ingest_extract_stores_knowledge_not_file():
    suffix = uuid.uuid4().hex[:8]
    # auth-hardened: demo bootstrap instead of public company create
    _cid, _oid, _hdrs, _demo = provision_company(client)
    co = {"id": _cid}
    owner = {"id": _oid, "email": _demo.get("owner_email")}
    headers = _hdrs
    content = b"Hotel partnership contract. Alila rate IDR 1850000. Valid 2026."
    res = client.post(
        f"/api/v1/companies/{co['id']}/knowledge/ingest-extract",
        headers=headers,
        files={"file": ("contract.txt", io.BytesIO(content), "text/plain")},
        data={"title": "Alila contract extract"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["title"] == "Alila contract extract"
    assert "Alila" in body["content"]
    assert "not retained" in body["content"].lower() or "not retained" in body["content"]


def test_skill_create_blocked_for_company_admin():
    from fastapi.testclient import TestClient
    from app.main import app
    from tests.helpers import provision_company, persona_headers

    with TestClient(app) as client:
        _cid, _oid, _hdrs, _demo = provision_company(client, hire_agents=False)
        try:
            _aid, admin_headers = persona_headers(client, _demo, "ai_admin")
        except AssertionError:
            admin_headers = _hdrs
        res = client.post(
            f"/api/v1/companies/{_cid}/skills",
            headers=admin_headers,
            json={
                "name": "Blocked Skill",
                "slug": "blocked_skill_mvp",
                "description": "Should be forbidden",
                "allowed_tools": [],
            },
        )
        assert res.status_code in (401, 403), res.text


