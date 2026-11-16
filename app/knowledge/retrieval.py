"""Knowledge retrieval — keyword baseline + optional hybrid vector (Job 26)."""

from __future__ import annotations

import re
import hashlib
from datetime import datetime, timezone

from sqlalchemy import and_, false, or_, select
from sqlalchemy.orm import Session

from app.models.entities import AgentMemory, DocumentStatus, KnowledgeChunk, KnowledgeDocument, KnowledgeItem
from app.security.knowledge_access import authorized_source_ids


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


def _normalized_hash(content: str) -> str:
    normalized = re.sub(r"\\s+", " ", (content or "").strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def deduplicate_source_hits(hits: list[dict]) -> list[dict]:
    """Keep the best-ranked passage per canonical source; retain cross-source provenance."""
    seen_sources: set[tuple[str, str]] = set()
    seen_hashes: set[tuple[str, str]] = set()
    result: list[dict] = []
    for hit in hits:
        source_type = hit.get("source_type")
        source_id = hit.get("source_id")
        if not source_type or not source_id:
            continue
        source_key = (str(source_type), str(source_id))
        passage_key = (str(source_id), _normalized_hash(str(hit.get("content") or "")))
        if source_key in seen_sources or passage_key in seen_hashes:
            continue
        seen_sources.add(source_key)
        seen_hashes.add(passage_key)
        result.append(hit)
    return result


def search_knowledge_chunks(
    db: Session,
    *,
    company_id: str,
    agent_instance_id: str | None,
    query: str,
    requester_id: str | None = None,
    purpose: str = "task_execution",
    limit: int = 5,
) -> list[dict]:
    item_ids, document_ids = authorized_source_ids(
        db,
        company_id=company_id,
        requester_id=requester_id,
        agent_instance_id=agent_instance_id,
        purpose=purpose,
    )
    if not item_ids and not document_ids:
        return []

    source_filters = []
    if item_ids:
        source_filters.append(
            and_(
                KnowledgeChunk.knowledge_item_id.is_not(None),
                KnowledgeChunk.knowledge_item_id.in_(item_ids),
            )
        )
    if document_ids:
        source_filters.append(
            and_(
                KnowledgeChunk.knowledge_document_id.is_not(None),
                KnowledgeChunk.knowledge_document_id.in_(document_ids),
            )
        )

    rows = list(
        db.scalars(
            select(KnowledgeChunk).where(
                KnowledgeChunk.company_id == company_id,
                KnowledgeChunk.is_active.is_(True),
                or_(
                    KnowledgeChunk.agent_instance_id.is_(None),
                    KnowledgeChunk.agent_instance_id == agent_instance_id,
                ),
                or_(*source_filters),
                or_(
                    KnowledgeChunk.knowledge_item_id.is_(None),
                    select(KnowledgeItem.id).where(
                        KnowledgeItem.id == KnowledgeChunk.knowledge_item_id,
                        KnowledgeItem.company_id == company_id,
                        KnowledgeItem.is_active.is_(True),
                        KnowledgeItem.id.in_(item_ids) if item_ids else false(),
                        or_(
                            KnowledgeItem.agent_instance_id.is_(None),
                            KnowledgeItem.agent_instance_id == agent_instance_id,
                        ),
                    ).exists(),
                ),
                or_(
                    KnowledgeChunk.knowledge_document_id.is_(None),
                    select(KnowledgeDocument.id).where(
                        KnowledgeDocument.id == KnowledgeChunk.knowledge_document_id,
                        KnowledgeDocument.company_id == company_id,
                        KnowledgeDocument.status == DocumentStatus.READY,
                        KnowledgeDocument.id.in_(document_ids) if document_ids else false(),
                        or_(
                            KnowledgeDocument.agent_instance_id.is_(None),
                            KnowledgeDocument.agent_instance_id == agent_instance_id,
                        ),
                    ).exists(),
                ),
            )
        ).all()
    )

    use_vector = _vector_enabled()
    query_emb = None
    kw_w = 1.0
    vec_w = 0.0
    if use_vector:
        from app.core.config import settings as live
        from app.knowledge.embeddings import get_embedding_provider

        provider = get_embedding_provider()
        query_emb = provider.embed(query)
        kw_w = float(live.hybrid_keyword_weight)
        vec_w = float(live.hybrid_vector_weight)
        total_w = kw_w + vec_w or 1.0
        kw_w, vec_w = kw_w / total_w, vec_w / total_w

    scored = []
    for row in rows:
        kw = score_text(query, row.content)
        vec = 0.0
        if use_vector and query_emb and row.embedding:
            from app.knowledge.embeddings import cosine_similarity
            vec = max(0.0, cosine_similarity(query_emb, row.embedding))
        if use_vector:
            score = kw_w * kw + vec_w * vec
            if score <= 0 and vec <= 0 and kw <= 0:
                continue
        else:
            score = kw
            if score <= 0:
                continue
        source_type = "item" if row.knowledge_item_id else "document"
        source_id = row.knowledge_item_id or row.knowledge_document_id
        scored.append((score, kw, vec, row, source_type, source_id))

    scored.sort(key=lambda value: value[0], reverse=True)
    ranked = []
    for score, kw, vec, row, source_type, source_id in scored:
        hit = {
            "id": row.id,
            "content": row.content,
            "score": round(score, 4),
            "chunk_index": row.chunk_index,
            "knowledge_item_id": row.knowledge_item_id,
            "knowledge_document_id": row.knowledge_document_id,
            "source_type": source_type,
            "source_id": source_id,
            "source": "chunk",
        }
        if use_vector:
            hit["keyword_score"] = round(kw, 4)
            hit["vector_score"] = round(vec, 4)
            hit["search_mode"] = "hybrid"
        else:
            hit["search_mode"] = "keyword"
        ranked.append(hit)

    return deduplicate_source_hits(ranked)[:limit]


def search_knowledge_items(
    db: Session,
    *,
    company_id: str,
    agent_instance_id: str | None,
    query: str,
    requester_id: str | None = None,
    purpose: str = "knowledge_search",
    limit: int = 5,
) -> list[dict]:
    item_ids, _ = authorized_source_ids(
        db,
        company_id=company_id,
        requester_id=requester_id,
        agent_instance_id=agent_instance_id,
        purpose=purpose,
    )
    if not item_ids:
        return []
    rows = list(
        db.scalars(
            select(KnowledgeItem).where(
                KnowledgeItem.id.in_(item_ids),
                KnowledgeItem.company_id == company_id,
                KnowledgeItem.is_active.is_(True),
                or_(
                    KnowledgeItem.agent_instance_id.is_(None),
                    KnowledgeItem.agent_instance_id == agent_instance_id,
                ),
            )
        ).all()
    )
    scored = []
    for row in rows:
        score = score_text(query, f"{row.title} {row.content}")
        if score > 0:
            scored.append((score, row))
    scored.sort(key=lambda value: value[0], reverse=True)
    return [
        {
            "id": row.id,
            "content": row.content,
            "title": row.title,
            "score": round(score, 4),
            "source_type": "item",
            "source_id": row.id,
            "source": "item",
            "search_mode": "keyword",
        }
        for score, row in scored[:limit]
    ]


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
