"""Knowledge retrieval — keyword baseline + optional hybrid vector (Job 26)."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.entities import AgentMemory, KnowledgeChunk, KnowledgeItem


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


def search_knowledge_chunks(
    db: Session,
    *,
    company_id: str,
    agent_instance_id: str | None,
    query: str,
    limit: int = 5,
) -> list[dict]:
    rows = list(
        db.scalars(
            select(KnowledgeChunk).where(
                KnowledgeChunk.company_id == company_id,
                KnowledgeChunk.is_active.is_(True),
                or_(
                    KnowledgeChunk.agent_instance_id.is_(None),
                    KnowledgeChunk.agent_instance_id == agent_instance_id,
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
        from app.knowledge.embeddings import cosine_similarity, get_embedding_provider

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
            s = kw_w * kw + vec_w * vec
            # keep weak semantic hits even without keyword overlap
            if s <= 0 and vec <= 0 and kw <= 0:
                continue
        else:
            s = kw
            if s <= 0:
                continue
        scored.append((s, kw, vec, row))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for s, kw, vec, row in scored[:limit]:
        hit = {
            "id": row.id,
            "content": row.content,
            "score": round(s, 4),
            "chunk_index": row.chunk_index,
            "knowledge_item_id": row.knowledge_item_id,
            "knowledge_document_id": row.knowledge_document_id,
            "source": "chunk",
        }
        if use_vector:
            hit["keyword_score"] = round(kw, 4)
            hit["vector_score"] = round(vec, 4)
            hit["search_mode"] = "hybrid"
        else:
            hit["search_mode"] = "keyword"
        results.append(hit)
    return results


def search_knowledge_items(
    db: Session,
    *,
    company_id: str,
    agent_instance_id: str | None,
    query: str,
    limit: int = 5,
) -> list[dict]:
    rows = list(
        db.scalars(
            select(KnowledgeItem).where(
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
        s = score_text(query, f"{row.title} {row.content}")
        if s > 0:
            scored.append((s, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for s, row in scored[:limit]:
        results.append(
            {
                "id": row.id,
                "content": row.content,
                "title": row.title,
                "score": round(s, 4),
                "source": "item",
                "search_mode": "keyword",
            }
        )
    return results


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
        if row.expires_at and row.expires_at < now:
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
