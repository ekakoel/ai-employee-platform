"""Fail-closed authorization for knowledge source retrieval."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import KnowledgeSourcePolicy, User


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
    for policy in policies:
        if policy.classification not in {"A", "B", "C"}:
            continue
        if not policy.approval_ref or purpose not in (policy.allowed_purposes or []):
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
