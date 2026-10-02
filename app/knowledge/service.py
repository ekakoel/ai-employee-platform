from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from app.knowledge.extractor import extract_text
from app.models.entities import DocumentStatus, KnowledgeDocument


DOCUMENT_STORAGE_ROOT = Path("storage/documents")


def ensure_storage_directory() -> None:
    DOCUMENT_STORAGE_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )


def save_document(
    db: Session,
    *,
    company_id: str,
    agent_instance_id: str | None,
    original_filename: str,
    content_type: str,
    data: bytes,
) -> KnowledgeDocument:
    ensure_storage_directory()

    document_id = str(uuid4())

    extension = Path(original_filename).suffix.lower()

    stored_filename = f"{document_id}{extension}"

    stored_path = DOCUMENT_STORAGE_ROOT / stored_filename

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

    try:
        stored_path.write_bytes(data)

        extracted_text = extract_text(
            original_filename,
            data,
        )

        document.extracted_text = extracted_text
        document.status = DocumentStatus.READY
        document.error_message = None

    except Exception as exc:
        document.status = DocumentStatus.FAILED
        document.error_message = str(exc)

    db.flush()

    return document