"""RET-001: fail-closed source authorization and duplicate-chunk tests."""
from datetime import datetime, timedelta, timezone
import hashlib

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.knowledge.retrieval import search_knowledge_chunks
from app.models.entities import (
    AuditLog, Company, KnowledgeChunk, KnowledgeItem, KnowledgeSourcePolicy,
    Role, User,
)
from app.security.knowledge_access import authorized_source_ids


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def _identity(db):
    company = Company(name="RET-001 Test Company")
    role = Role(name="owner")
    db.add_all([company, role])
    db.flush()
    user = User(
        company_id=company.id, email="owner@example.test", name="Test Owner",
        role_id=role.id, status="active",
    )
    db.add(user)
    db.flush()
    return company, user


def _policy(db, company, user, item, *, classification="B",
            users=None, purposes=None, active=True, expires_at=None):
    policy = KnowledgeSourcePolicy(
        company_id=company.id,
        source_type="item",
        source_id=item.id,
        source_hash=hashlib.sha256(item.content.encode("utf-8")).hexdigest(),
        classification=classification,
        is_approved=True,
        is_active=active,
        allowed_user_ids=users or [],
        allowed_role_ids=[],
        allowed_department_ids=[],
        allowed_purposes=purposes or ["task_execution"],
        policy_version=1,
        approval_ref="TEST-APPROVAL-001",
        owner_user_id=user.id,
        reviewed_at=datetime.now(timezone.utc),
        expires_at=expires_at,
    )
    db.add(policy)
    db.flush()
    return policy


def test_unknown_requester_and_missing_policy_fail_closed():
    engine, db = _session()
    try:
        company, user = _identity(db)
        item = KnowledgeItem(company_id=company.id, title="Internal", content="internal booking rule")
        db.add(item)
        db.flush()
        assert authorized_source_ids(db, requester=None, company_id=company.id, purpose="task_execution") == ([], [])
        assert authorized_source_ids(db, requester=user, company_id=company.id, purpose="task_execution") == ([], [])
    finally:
        db.close()
        engine.dispose()


def test_b_and_c_require_explicit_identity_and_purpose_grants():
    engine, db = _session()
    try:
        company, user = _identity(db)
        item_b = KnowledgeItem(company_id=company.id, title="B", content="internal")
        item_c = KnowledgeItem(company_id=company.id, title="C", content="restricted")
        db.add_all([item_b, item_c])
        db.flush()
        _policy(db, company, user, item_b, classification="B")
        _policy(db, company, user, item_c, classification="C", users=[user.id], purposes=["reservation_case"])
        assert authorized_source_ids(db, requester=user, company_id=company.id, purpose="task_execution") == ([item_b.id], [])
        assert authorized_source_ids(db, requester=user, company_id=company.id, purpose="reservation_case") == ([item_b.id, item_c.id], [])
    finally:
        db.close()
        engine.dispose()


def test_d_u_revoked_and_expired_sources_are_never_authorized():
    engine, db = _session()
    try:
        company, user = _identity(db)
        items = [
            KnowledgeItem(company_id=company.id, title=f"Source {kind}", content="test")
            for kind in ("D", "U", "revoked", "expired")
        ]
        db.add_all(items)
        db.flush()
        _policy(db, company, user, items[0], classification="D", users=[user.id])
        _policy(db, company, user, items[1], classification="U", users=[user.id])
        _policy(db, company, user, items[2], users=[user.id], active=False)
        _policy(db, company, user, items[3], users=[user.id], expires_at=datetime.now(timezone.utc) - timedelta(days=1))
        assert authorized_source_ids(db, requester=user, company_id=company.id, purpose="task_execution") == ([], [])
    finally:
        db.close()
        engine.dispose()


def test_exact_duplicate_chunks_removed_but_distinct_source_provenance_preserved(monkeypatch):
    engine, db = _session()
    try:
        company, user = _identity(db)
        first = KnowledgeItem(company_id=company.id, title="First policy", content="Cancellation is free within 24 hours.")
        second = KnowledgeItem(company_id=company.id, title="Second policy", content="Cancellation is free within 24 hours.")
        db.add_all([first, second])
        db.flush()
        _policy(db, company, user, first, users=[user.id])
        _policy(db, company, user, second, users=[user.id])
        db.add_all([
            KnowledgeChunk(company_id=company.id, knowledge_item_id=first.id, content="Cancellation is free within 24 hours.", chunk_index=0),
            KnowledgeChunk(company_id=company.id, knowledge_item_id=first.id, content="  cancellation   is FREE within 24 hours. ", chunk_index=1),
            KnowledgeChunk(company_id=company.id, knowledge_item_id=second.id, content="Cancellation is free within 24 hours.", chunk_index=0),
        ])
        db.flush()
        monkeypatch.setattr("app.knowledge.retrieval._vector_enabled", lambda: False)
        hits = search_knowledge_chunks(
            db, company_id=company.id, agent_instance_id=None,
            query="cancellation free hours", requester_user_id=user.id,
            purpose="task_execution", limit=5,
        )
        assert len(hits) == 2
        assert {hit["source_id"] for hit in hits} == {first.id, second.id}
        assert {hit["source_title"] for hit in hits} == {"First policy", "Second policy"}
        audit = db.scalars(select(AuditLog).where(AuditLog.action == "knowledge.retrieval")).all()
        assert audit
        assert all("query" not in (row.details or {}) for row in audit)
        assert all("content" not in (row.details or {}) for row in audit)
    finally:
        db.close()
        engine.dispose()
