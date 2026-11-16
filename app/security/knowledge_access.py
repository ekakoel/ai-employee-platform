"""Fail-closed authorization for knowledge source retrieval."""
from datetime import datetime, timezone
import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import KnowledgeDocument, KnowledgeItem, KnowledgeSourcePolicy, User


def authorized_source_ids(
    db: Session,
    *,
    requester: User | None,
    company_id: str,
    purpose: str,
) -> tuple[list[str], list[str]]:
    """Resolve explicit source grants from trusted persisted identity; unknown is deny."""
    if (
        requester is None
        or requester.status != "active"
        or requester.company_id != company_id
        or not purpose
    ):
        return [], []

    now = datetime.now(timezone.utc)
    policies = db.scalars(
        select(KnowledgeSourcePolicy).where(
            KnowledgeSourcePolicy.company_id == company_id,
            KnowledgeSourcePolicy.is_active.is_(True),
            KnowledgeSourcePolicy.is_approved.is_(True),
            KnowledgeSourcePolicy.owner_user_id.is_not(None),
            KnowledgeSourcePolicy.reviewed_at.is_not(None),
            (KnowledgeSourcePolicy.expires_at.is_(None))
            | (KnowledgeSourcePolicy.expires_at > now),
        )
    ).all()

    item_ids: list[str] = []
    document_ids: list[str] = []
    candidate_item_ids = [p.source_id for p in policies if p.source_type == "item"]
    candidate_document_ids = [p.source_id for p in policies if p.source_type == "document"]
    item_rows = {
        row.id: row for row in db.scalars(
            select(KnowledgeItem).where(
                KnowledgeItem.company_id == company_id,
                KnowledgeItem.id.in_(candidate_item_ids or ["__deny__"]),
            )
        ).all()
    }
    document_rows = {
        row.id: row for row in db.scalars(
            select(KnowledgeDocument).where(
                KnowledgeDocument.company_id == company_id,
                KnowledgeDocument.id.in_(candidate_document_ids or ["__deny__"]),
            )
        ).all()
    }
    for policy in policies:
        if policy.classification not in {"A", "B", "C"}:
            continue
        if not policy.approval_ref or not policy.source_hash or purpose not in (policy.allowed_purposes or []):
            continue
        source = item_rows.get(policy.source_id) if policy.source_type == "item" else document_rows.get(policy.source_id)
        if source is None or not getattr(source, "is_active", True):
            continue
        if policy.source_type == "document" and str(source.status).lower() not in {"ready", "documentstatus.ready"}:
            continue
        source_text = source.content if policy.source_type == "item" else (source.extracted_text or "")
        current_hash = hashlib.sha256((source_text or "").encode("utf-8")).hexdigest()
        if current_hash != policy.source_hash:
            continue
        if policy.classification in {"B", "C"}:
            user_grant = requester.id in (policy.allowed_user_ids or [])
            role_grant = requester.role_id in (policy.allowed_role_ids or [])
            department_grant = bool(
                requester.department_id
                and requester.department_id in (policy.allowed_department_ids or [])
            )
            if not (user_grant or role_grant or department_grant):
                continue
        if policy.source_type == "item":
            item_ids.append(policy.source_id)
        elif policy.source_type == "document":
            document_ids.append(policy.source_id)
    return item_ids, document_ids
