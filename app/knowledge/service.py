from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from app.knowledge.extractor import extract_text
from app.knowledge.indexing import replace_chunks_for_document
from app.models.entities import DocumentStatus, KnowledgeDocument
from app.storage import get_storage


def save_document(
    db: Session,
    *,
    company_id: str,
    data: bytes,
    original_filename: str,
    content_type: str | None = None,
    agent_instance_id: str | None = None,
) -> KnowledgeDocument:
    """
    Persist uploaded document bytes via ObjectStorage (local or S3)
    and extract text for indexing.
    """
    document_id = str(uuid4())
    extension = ""
    if "." in original_filename:
        extension = "." + original_filename.rsplit(".", 1)[-1].lower()

    stored_filename = f"{document_id}{extension}"
    # Tenant-prefixed key for multi-tenant isolation in shared buckets
    storage_key = f"documents/{company_id}/{stored_filename}"

    document = KnowledgeDocument(
        id=document_id,
        company_id=company_id,
        agent_instance_id=agent_instance_id,
        original_filename=original_filename,
        stored_filename=stored_filename,
        content_type=content_type or "application/octet-stream",
        file_size=len(data),
        status=DocumentStatus.PROCESSING,
    )

    db.add(document)
    db.flush()

    storage = get_storage()
    try:
        storage.put_bytes(
            storage_key,
            data,
            content_type=document.content_type,
        )

        extracted_text = extract_text(
            original_filename,
            data,
        )

        document.extracted_text = extracted_text
        document.status = DocumentStatus.READY
        document.error_message = None
        replace_chunks_for_document(db, document)

    except Exception as exc:
        document.status = DocumentStatus.FAILED
        document.error_message = str(exc)
        # best-effort cleanup
        try:
            storage.delete(storage_key)
        except Exception:
            pass

    db.flush()

    return document



def ingest_document_to_knowledge(
    db: Session,
    *,
    company_id: str,
    data: bytes,
    original_filename: str,
    content_type: str | None = None,
    agent_instance_id: str | None = None,
    created_by_user_id: str | None = None,
    title: str | None = None,
    category: str = "document",
):
    """Extract text from an uploaded file and store **only** knowledge (item + chunks).

    Original file bytes are **not** written to object storage or disk (MVP).
    """
    from app.models.entities import KnowledgeItem
    from app.knowledge.indexing import replace_chunks_for_item

    if not data:
        raise ValueError("Uploaded document is empty")

    extracted = extract_text(original_filename, data)
    if not (extracted or "").strip():
        raise ValueError("No extractable text found in document")

    item_title = (title or original_filename or "Uploaded document").strip()[:300]
    header = (
        f"[Extracted from {original_filename or 'document'}; "
        f"file not retained; {len(data)} bytes processed"
        f"{'; by ' + created_by_user_id if created_by_user_id else ''}]"
    )
    body = f"{header}\n\n{extracted.strip()}"

    item = KnowledgeItem(
        company_id=company_id,
        agent_instance_id=agent_instance_id,
        title=item_title,
        content=body,
        category=(category or "document")[:100],
        is_active=True,
    )
    db.add(item)
    db.flush()
    replace_chunks_for_item(db, item)
    return item
