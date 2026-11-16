"""Knowledge retrieval — keyword baseline + optional hybrid vector (Job 26)."""

from __future__ import annotations

import re
import hashlib
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.entities import AgentMemory, AuditLog, KnowledgeChunk, KnowledgeDocument, KnowledgeItem, KnowledgeSourcePolicy, User


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-zA-Z0-9_]{2,}", (text or "").lower())}


def score_text(query: str, content: str) -> float:
    q = _tokens(query)
    if not q:
        return 0.0
    c = _tokens(content)
    if not c:
        return 0.0
    overlap = q & c
    return len(overlap) / len(q)


def _vector_enabled() -> bool:
    from app.core.config import settings as live

    return bool(live.knowledge_vector)



def _record_retrieval_audit(db: Session, *, requester: User | None, company_id: str,
                            purpose: str, allowed_sources: int, denied: bool = False) -> None:
    """Record metadata-only retrieval decisions; never persist query or passage text."""
    db.add(AuditLog(
        company_id=company_id,
        user_id=requester.id if requester else None,
        action="knowledge.retrieval",
        resource_type="knowledge_source",
        status="denied" if denied else "success",
        details={
            "purpose": purpose,
            "allowed_source_count": allowed_sources,
            "reason": "requester_missing_or_inactive" if denied else "authorized_sources_only",
        },
    ))
    db.flush()


def authorized_source_ids(db: Session, *, requester: User | None,
                          company_id: str, purpose: str) -> tuple[list[str], list[str]]:
    """Resolve explicit source grants from trusted persisted identity; unknown is deny."""
    if (requester is None or requester.status != "active"
            or requester.company_id != company_id or not purpose):
        return [], []
    policies = db.scalars(select(KnowledgeSourcePolicy).where(
        KnowledgeSourcePolicy.company_id == company_id,
        KnowledgeSourcePolicy.is_active.is_(True),
        KnowledgeSourcePolicy.is_approved.is_(True),
        KnowledgeSourcePolicy.expires_at.is_(None) | (KnowledgeSourcePolicy.expires_at > datetime.now(timezone.utc)),
        KnowledgeSourcePolicy.allowed_purposes.contains([purpose]),
    )).all()
    item_ids: list[str] = []
    document_ids: list[str] = []
    for policy in policies:
        if policy.classification not in {"A", "B", "C"}:
            continue
        if policy.classification in {"B", "C"}:
            user_grant = requester.id in (policy.allowed_user_ids or [])
            role_grant = requester.role_id in (policy.allowed_role_ids or [])
            department_grant = bool(requester.department_id and requester.department_id in (policy.allowed_department_ids or []))
            if not (user_grant or role_grant or department_grant):
                continue
        if policy.source_type == "item":
            item_ids.append(policy.source_id)
        elif policy.source_type == "document":
            document_ids.append(policy.source_id)
    return item_ids, document_ids


def search_knowledge_chunks(
    db: Session,
    *,
    company_id: str,
    agent_instance_id: str | None,
    query: str,
    limit: int = 5,
    requester_user_id: str | None = None,
    purpose: str = "task_execution",
) -> list[dict]:
    # Never query chunks without a persisted, active requester identity.
    requester = db.get(User, requester_user_id) if requester_user_id else None
    item_ids, document_ids = authorized_source_ids(
        db, requester=requester, company_id=company_id, purpose=purpose
    )
    if not item_ids and not document_ids:
        _record_retrieval_audit(
            db, requester=requester, company_id=company_id,
            purpose=purpose, allowed_sources=0, denied=True,
        )
        return []

    source_filter = []
    if item_ids:
        source_filter.append(KnowledgeChunk.knowledge_item_id.in_(item_ids))
    if document_ids:
        source_filter.append(KnowledgeChunk.knowledge_document_id.in_(document_ids))

    rows = list(db.scalars(
        select(KnowledgeChunk).where(
            KnowledgeChunk.company_id == company_id,
            KnowledgeChunk.is_active.is_(True),
            KnowledgeChunk.agent_instance_id.is_(None) | (KnowledgeChunk.agent_instance_id == agent_instance_id),
            or_(*source_filter),
            or_(
                KnowledgeChunk.knowledge_item_id.is_(None),
                select(KnowledgeItem.id).where(
                    KnowledgeItem.id == KnowledgeChunk.knowledge_item_id,
                    KnowledgeItem.company_id == company_id,
                    KnowledgeItem.is_active.is_(True),
                    KnowledgeItem.id.in_(item_ids or ["__deny__"]),
                    KnowledgeItem.agent_instance_id.is_(None) | (KnowledgeItem.agent_instance_id == agent_instance_id),
                ).exists(),
            ),
            or_(
                KnowledgeChunk.knowledge_document_id.is_(None),
                select(KnowledgeDocument.id).where(
                    KnowledgeDocument.id == KnowledgeChunk.knowledge_document_id,
                    KnowledgeDocument.company_id == company_id,
                    KnowledgeDocument.status == "ready",
                    KnowledgeDocument.id.in_(document_ids or ["__deny__"]),
                    KnowledgeDocument.agent_instance_id.is_(None) | (KnowledgeDocument.agent_instance_id == agent_instance_id),
                ).exists(),
            ),
        )
    ).all())

    use_vector = _vector_enabled()
    query_emb = None
    kw_w, vec_w = 1.0, 0.0
    if use_vector:
        from app.core.config import settings as live
        from app.knowledge.embeddings import get_embedding_provider
        query_emb = get_embedding_provider().embed(query)
        kw_w, vec_w = float(live.hybrid_keyword_weight), float(live.hybrid_vector_weight)
        total_w = kw_w + vec_w or 1.0
        kw_w, vec_w = kw_w / total_w, vec_w / total_w

    scored = []
    seen_passages: set[tuple[str, str]] = set()
    for row in rows:
        source_key = f"item:{row.knowledge_item_id}" if row.knowledge_item_id else f"document:{row.knowledge_document_id}"
        normalized = " ".join((row.content or "").lower().split())
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        duplicate_key = (source_key, digest)
        if duplicate_key in seen_passages:
            continue
        seen_passages.add(duplicate_key)
        kw = score_text(query, row.content)
        vec = 0.0
        if use_vector and query_emb and row.embedding:
            from app.knowledge.embeddings import cosine_similarity
            vec = max(0.0, cosine_similarity(query_emb, row.embedding))
        score = kw_w * kw + vec_w * vec if use_vector else kw
        if score <= 0:
            continue
        scored.append((score, kw, vec, row, source_key))

    scored.sort(key=lambda x: x[0], reverse=True)
    # Default: one highest-ranked passage per canonical source.
    selected, seen_sources = [], set()
    for entry in scored:
        if entry[4] in seen_sources:
            continue
        selected.append(entry)
        seen_sources.add(entry[4])
        if len(selected) >= max(1, limit):
            break

    item_titles = {x.id: x.title for x in db.scalars(select(KnowledgeItem).where(KnowledgeItem.id.in_(item_ids or ["__deny__"]))).all()}
    doc_titles = {x.id: x.original_filename for x in db.scalars(select(KnowledgeDocument).where(KnowledgeDocument.id.in_(document_ids or ["__deny__"]))).all()}
    results = []
    for score, kw, vec, row, source_key in selected:
        source_id = row.knowledge_item_id or row.knowledge_document_id
        title = item_titles.get(source_id) or doc_titles.get(source_id) or "Knowledge source"
        hit = {
            "id": row.id, "content": row.content, "score": round(score, 4),
            "chunk_index": row.chunk_index, "knowledge_item_id": row.knowledge_item_id,
            "knowledge_document_id": row.knowledge_document_id, "source": "chunk",
            "source_id": source_id, "source_title": title,
        }
        if use_vector:
            hit.update({"keyword_score": round(kw, 4), "vector_score": round(vec, 4), "search_mode": "hybrid"})
        else:
            hit["search_mode"] = "keyword"
        results.append(hit)

    _record_retrieval_audit(
        db, requester=requester, company_id=company_id, purpose=purpose,
        allowed_sources=len(seen_sources), denied=False,
    )
    return results


def search_knowledge_items(
    db: Session,
    *,
    company_id: str,
    agent_instance_id: str | None,
    query: str,
    limit: int = 5,
    requester_user_id: str | None = None,
    purpose: str = "task_execution",
) -> list[dict]:
    requester = db.get(User, requester_user_id) if requester_user_id else None
    item_ids, _ = authorized_source_ids(db, requester=requester, company_id=company_id, purpose=purpose)
    if not item_ids:
        return []
    rows = list(db.scalars(select(KnowledgeItem).where(
        KnowledgeItem.id.in_(item_ids),
        KnowledgeItem.company_id == company_id,
        KnowledgeItem.is_active.is_(True),
        KnowledgeItem.agent_instance_id.is_(None) | (KnowledgeItem.agent_instance_id == agent_instance_id),
    )).all())
    scored = []
    for row in rows:
        score = score_text(query, f"{row.title} {row.content}")
        if score > 0:
            scored.append((score, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{
        "id": row.id, "content": row.content, "title": row.title,
        "score": round(score, 4), "source": "item", "source_id": row.id,
    } for score, row in scored[:max(1, limit)]]


def search_agent_memories(
    db: Session,
    *,
    company_id: str,
    agent_instance_id: str,
    query: str,
    limit: int = 5,
) -> list[dict]:
    now = datetime.now(timezone.utc)
    rows = list(
        db.scalars(
            select(AgentMemory).where(
                AgentMemory.company_id == company_id,
                AgentMemory.agent_instance_id == agent_instance_id,
                AgentMemory.is_active.is_(True),
            )
        ).all()
    )
    scored = []
    for row in rows:
        expires_at = row.expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at and expires_at <= now:
            continue
        s = score_text(query, f"{row.title} {row.content}")
        if s > 0:
            scored.append((s, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "id": row.id,
            "content": row.content,
            "title": row.title,
            "score": round(s, 4),
            "source": "memory",
        }
        for s, row in scored[:limit]
    ]



def active_agent_memories(
    db: Session,
    *,
    company_id: str,
    agent_instance_id: str,
    limit: int = 10,
) -> list[AgentMemory]:
    now = datetime.now(timezone.utc)
    rows = list(
        db.scalars(
            select(AgentMemory)
            .where(
                AgentMemory.company_id == company_id,
                AgentMemory.agent_instance_id == agent_instance_id,
                AgentMemory.is_active.is_(True),
            )
            .order_by(AgentMemory.updated_at.desc())
        ).all()
    )
    result = []
    for m in rows:
        if m.expires_at is not None:
            exp = m.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp <= now:
                continue
        result.append(m)
        if len(result) >= limit:
            break
    return result
