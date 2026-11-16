"""Job 77 — search_knowledge runtime E2E against seeded company knowledge."""
from __future__ import annotations

import os
import hashlib
from datetime import datetime, timezone

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
        pytest.skip(
            "demo bootstrap unavailable: %s %s" % (r.status_code, r.text[:200])
        )
    data = r.json()
    company_id = data.get("company_id") or (data.get("company") or {}).get("id")
    assert company_id, data
    agents = data.get("agents") or []
    agent_instance_id = None
    if isinstance(agents, list) and agents:
        first = agents[0]
        if isinstance(first, dict) and "id" in first:
            agent_instance_id = first["id"]
    return data, company_id, agent_instance_id


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


def _approve_demo_sources(company_id, owner_id, agent_instance_id):
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
            grant = KnowledgeSourceGrant(
                company_id=company_id,
                source_type="item",
                source_id=item.id,
                classification="B",
                owner_user_id=owner_id,
                created_by_user_id=owner_id,
                allowed_user_ids=[owner_id],
                allowed_agent_instance_ids=[agent_instance_id],
                allowed_purposes=["knowledge_search"],
                is_active=True,
                is_approved=True,
                policy_version=1,
                source_version=source_version_token(item.updated_at),
                source_hash=hashlib.sha256(item.content.encode("utf-8")).hexdigest(),
                approved_by_user_id=owner_id,
                approved_at=datetime.now(timezone.utc),
            )
            db.add(grant)
        db.flush()
        from app.knowledge.indexing import replace_chunks_for_item
        for item in items:
            replace_chunks_for_item(db, item)
        db.commit()


def _search(db, company_id, query, limit=5, agent_instance_id=None, requester_id=None):
    from app.knowledge.retrieval import search_knowledge_chunks
    return search_knowledge_chunks(
        db,
        company_id=company_id,
        query=query,
        agent_instance_id=agent_instance_id,
        requester_id=requester_id,
        purpose="knowledge_search",
        limit=limit,
    )


def test_search_knowledge_finds_cancellation_policy(client):
    """After bootstrap + index, keyword search finds cancellation_policy."""
    data, company_id, agent_instance_id = _bootstrap(client)
    owner_id = data.get("owner_user_id") or data.get("user_id")
    _approve_demo_sources(company_id, owner_id, agent_instance_id)
    SessionLocal = _session_local()
    if SessionLocal is None:
        pytest.skip("SessionLocal not found")

    db = SessionLocal()
    try:
        hits = _search(
            db,
            company_id,
            "cancellation policy free cancellation",
            agent_instance_id=agent_instance_id,
            requester_id=owner_id,
        )
        assert hits, "expected at least one hit for cancellation policy"
        blob = str(hits).lower()
        assert "cancel" in blob or "48" in blob or "refund" in blob
    finally:
        db.close()


def test_search_knowledge_finds_pricing_and_tax(client):
    """pricing_rules and tax_policy content are searchable."""
    data, company_id, agent_instance_id = _bootstrap(client)
    owner_id = data.get("owner_user_id") or data.get("user_id")
    _approve_demo_sources(company_id, owner_id, agent_instance_id)
    SessionLocal = _session_local()
    if SessionLocal is None:
        pytest.skip("SessionLocal not found")

    db = SessionLocal()
    try:
        pricing = _search(
            db,
            company_id,
            "pricing weekend surcharge",
            agent_instance_id=agent_instance_id,
            requester_id=owner_id,
        )
        tax = _search(
            db,
            company_id,
            "tax VAT PPN",
            agent_instance_id=agent_instance_id,
            requester_id=owner_id,
        )
        assert pricing or tax, "expected hits for pricing or tax knowledge"
        combined = (str(pricing) + str(tax)).lower()
        assert any(
            k in combined
            for k in ("price", "weekend", "tax", "ppn", "vat", "11%")
        )
    finally:
        db.close()


def test_empty_query_does_not_crash(client):
    _, company_id, agent_instance_id = _bootstrap(client)
    SessionLocal = _session_local()
    if SessionLocal is None:
        pytest.skip("SessionLocal not found")

    db = SessionLocal()
    try:
        hits = _search(
            db,
            company_id,
            "",
            agent_instance_id=agent_instance_id,
        )
        assert hits is None or isinstance(hits, (list, tuple))
    finally:
        db.close()


def test_search_knowledge_tool_registered(client):
    r = client.get("/api/v1/tools")
    if r.status_code != 200:
        pytest.skip("tools catalog endpoint unavailable")
    names = {t.get("name") for t in r.json()}
    assert "search_knowledge" in names
    meta = next(t for t in r.json() if t.get("name") == "search_knowledge")
    assert meta.get("side_effect") in (False, None) or meta.get("read_only") is True
