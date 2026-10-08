"""Index knowledge items/documents into chunks."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.knowledge.chunking import chunk_text, estimate_tokens
from app.models.entities import KnowledgeChunk, KnowledgeDocument, KnowledgeItem


def _maybe_embed(content: str) -> tuple[list[float] | None, str | None]:
    from app.core.config import settings as live

    if not live.knowledge_vector:
        return None, None
    from app.knowledge.embeddings import get_embedding_provider

    provider = get_embedding_provider()
    return provider.embed(content), provider.model_name


def replace_chunks_for_item(db: Session, item: KnowledgeItem) -> list[KnowledgeChunk]:
    existing = list(
        db.scalars(
            select(KnowledgeChunk).where(
                KnowledgeChunk.knowledge_item_id == item.id
            )
        ).all()
    )
    for e in existing:
        db.delete(e)
    db.flush()

    parts = chunk_text(item.content)
    created: list[KnowledgeChunk] = []
    for i, part in enumerate(parts):
        emb, model = _maybe_embed(part)
        chunk = KnowledgeChunk(
            company_id=item.company_id,
            agent_instance_id=item.agent_instance_id,
            knowledge_item_id=item.id,
            knowledge_document_id=None,
            chunk_index=i,
            content=part,
            token_estimate=estimate_tokens(part),
            embedding=emb,
            embedding_model=model,
            is_active=item.is_active,
        )
        db.add(chunk)
        created.append(chunk)
    db.flush()
    return created


def replace_chunks_for_document(
    db: Session, document: KnowledgeDocument
) -> list[KnowledgeChunk]:
    existing = list(
        db.scalars(
            select(KnowledgeChunk).where(
                KnowledgeChunk.knowledge_document_id == document.id
            )
        ).all()
    )
    for e in existing:
        db.delete(e)
    db.flush()

    text = document.extracted_text or ""
    parts = chunk_text(text)
    created: list[KnowledgeChunk] = []
    for i, part in enumerate(parts):
        emb, model = _maybe_embed(part)
        chunk = KnowledgeChunk(
            company_id=document.company_id,
            agent_instance_id=document.agent_instance_id,
            knowledge_item_id=None,
            knowledge_document_id=document.id,
            chunk_index=i,
            content=part,
            token_estimate=estimate_tokens(part),
            embedding=emb,
            embedding_model=model,
            is_active=True,
        )
        db.add(chunk)
        created.append(chunk)
    db.flush()
    return created
