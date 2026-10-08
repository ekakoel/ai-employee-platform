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
