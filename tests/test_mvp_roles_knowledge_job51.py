"""Job 51 — company role matrix, ephemeral knowledge ingest, platform-only skill create."""

import io
import uuid

from fastapi.testclient import TestClient

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
    co = client.post("/api/v1/companies", json={"name": f"Know {suffix}"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={
            "name": "CM",
            "email": f"cm-{suffix}@k51.test",
            "role": "contract_manager",
            "password": "demo12345",
        },
    ).json()
    headers = {"X-User-ID": owner["id"]}
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
    suffix = uuid.uuid4().hex[:8]
    co = client.post("/api/v1/companies", json={"name": f"Skill {suffix}"}).json()
    admin = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={
            "name": "AI Admin",
            "email": f"ai-{suffix}@k51.test",
            "role": "ai_admin",
            "password": "demo12345",
        },
    ).json()
    res = client.post(
        f"/api/v1/companies/{co['id']}/skills",
        headers={"X-User-ID": admin["id"]},
        json={
            "slug": f"custom-{suffix}",
            "name": "Custom skill",
            "description": "should fail",
        },
    )
    assert res.status_code == 403, res.text
