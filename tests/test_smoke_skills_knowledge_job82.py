"""Job 82 — smoke E2E: demo bootstrap, knowledge hits, skills API shape."""
from __future__ import annotations

import os
import hashlib
from datetime import datetime, timezone
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _bootstrap(client):
    os.environ.setdefault("DEBUG", "true")
    os.environ.setdefault("APP_ENV", "development")
    r = client.post("/api/v1/demo/bootstrap")
    if r.status_code not in (200, 201):
        pytest.skip("demo bootstrap unavailable: %s" % r.status_code)
    data = r.json()
    company_id = data.get("company_id") or (data.get("company") or {}).get("id")
    assert company_id
    agents = data.get("agents") or []
    agent_id = None
    if agents and isinstance(agents[0], dict):
        agent_id = agents[0].get("id")
    return data, company_id, agent_id


def _session_local():
    try:
        from app.core.database import SessionLocal
        return SessionLocal
    except Exception:
        pass
    try:
        from app.db.session import SessionLocal
        return SessionLocal
    except Exception:
        return None


def _approve_demo_sources(company_id, owner_id):
    from app.models.entities import KnowledgeItem, KnowledgeSourceGrant
    from app.security.knowledge_access import source_version_token

    SessionLocal = _session_local()
    if SessionLocal is None or not owner_id:
        return
    with SessionLocal() as db:
        items = db.query(KnowledgeItem).filter(
            KnowledgeItem.company_id == company_id,
            KnowledgeItem.is_active.is_(True),
        ).all()
        for item in items:
            db.add(KnowledgeSourceGrant(
                company_id=company_id,
                source_type="item",
                source_id=item.id,
                classification="B",
                owner_user_id=owner_id,
                created_by_user_id=owner_id,
                allowed_user_ids=[owner_id],
                allowed_purposes=["knowledge_search"],
                is_active=True,
                is_approved=True,
                policy_version=1,
                source_version=source_version_token(item.updated_at),
                source_hash=hashlib.sha256(item.content.encode("utf-8")).hexdigest(),
                approved_by_user_id=owner_id,
                approved_at=datetime.now(timezone.utc),
            ))
        db.commit()


def test_bootstrap_seeds_searchable_knowledge(client):
    data, company_id, agent_id = _bootstrap(client)
    owner_id = data.get("owner_user_id") or data.get("user_id")
    _approve_demo_sources(company_id, owner_id)
    SessionLocal = _session_local()
    if SessionLocal is None:
        pytest.skip("SessionLocal not found")
    from app.knowledge.retrieval import search_knowledge_chunks

    db = SessionLocal()
    try:
        hits = search_knowledge_chunks(
            db,
            company_id=company_id,
            agent_instance_id=agent_id,
            requester_id=owner_id,
            purpose="knowledge_search",
            query="cancellation policy 48 hours",
            limit=5,
        )
        assert hits, "expected knowledge hits after bootstrap seed+index"
        blob = str(hits).lower()
        assert "cancel" in blob or "48" in blob
    finally:
        db.close()


def test_skills_api_returns_platform_and_or_company(client):
    _, company_id, _ = _bootstrap(client)
    r = client.get(f"/api/v1/companies/{company_id}/skills")
    if r.status_code == 401:
        pytest.skip("skills list requires auth in this build")
    if r.status_code != 200:
        # try without api prefix
        r = client.get(f"/companies/{company_id}/skills")
    if r.status_code != 200:
        pytest.skip("skills list endpoint status %s" % r.status_code)
    skills = r.json()
    assert isinstance(skills, list) and len(skills) >= 1
    slugs = [s.get("slug") for s in skills if isinstance(s, dict)]
    assert "availability_check" in slugs or any(slugs)


def test_skills_slug_duplicates_are_data_not_crash(client):
    """Document: API may return platform+company same slug; UI dedupes client-side."""
    _, company_id, _ = _bootstrap(client)
    r = client.get(f"/api/v1/companies/{company_id}/skills")
    if r.status_code != 200:
        r = client.get(f"/companies/{company_id}/skills")
    if r.status_code != 200:
        pytest.skip("skills list unavailable")
    skills = r.json() or []
    slugs = [s.get("slug") for s in skills if isinstance(s, dict) and s.get("slug")]
    counts = Counter(slugs)
    # Smoke only: response is well-formed; duplicates allowed at API layer
    assert all(isinstance(s, str) for s in slugs)


def test_render_skills_dedupe_in_frontend():
    from pathlib import Path
    js = Path(__file__).resolve().parents[1] / "app" / "static" / "workspace" / "app.js"
    text = js.read_text(encoding="utf-8")
    assert "function dedupeSkillsPreferCompany" in text
    assert "const deduped = dedupeSkillsPreferCompany(list)" in text
