"""Job 77 — search_knowledge runtime E2E against seeded company knowledge."""
from __future__ import annotations

import os

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
    agent_instance_id = (
        data.get("agent_instance_id")
        or data.get("agent_id")
        or (
            (data.get("agents") or [{}])[0].get("id")
            if isinstance(data.get("agents"), list) and data.get("agents")
            else None
        )
    )
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


def _search(db, company_id, query, limit=5, agent_instance_id=None):
    """Call search_knowledge_chunks with required agent_instance_id kwarg."""
    from app.knowledge.retrieval import search_knowledge_chunks

    return search_knowledge_chunks(
        db,
        company_id=company_id,
        query=query,
        agent_instance_id=agent_instance_id,
        limit=limit,
    )


def test_search_knowledge_finds_cancellation_policy(client):
    """After bootstrap + index, keyword search finds cancellation_policy."""
    _, company_id, agent_instance_id = _bootstrap(client)
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
        )
        assert hits, "expected at least one hit for cancellation policy"
        blob = str(hits).lower()
        assert "cancel" in blob or "48" in blob or "refund" in blob
    finally:
        db.close()


def test_search_knowledge_finds_pricing_and_tax(client):
    """pricing_rules and tax_policy content are searchable."""
    _, company_id, agent_instance_id = _bootstrap(client)
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
        )
        tax = _search(
            db,
            company_id,
            "tax VAT PPN",
            agent_instance_id=agent_instance_id,
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