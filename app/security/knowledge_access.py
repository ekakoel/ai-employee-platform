"""Fail-closed authorization for knowledge source retrieval.

A chunk is readable only when its parent source has an active, approved grant
that matches the authenticated requester, agent, and declared purpose.
"""
from __future__ import annotations

from datetime import timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    AgentInstance,
    AuditLog,
    DocumentStatus,
    KnowledgeDocument,
    KnowledgeItem,
    KnowledgeSourceGrant,
    User,
)


def source_version_token(value: Any) -> str:
    """Stable timestamp token invalidating grants after a source edit."""
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return str(int(value.timestamp() * 1_000_000))


def grant_allows(grant: Any, user: Any, purpose: str) -> bool:
    """Pure policy predicate. Missing or malformed metadata always denies."""
    classification = str(getattr(grant, "classification", "") or "").upper()
    if classification not in {"A", "B", "C"}:
        return False
    if not getattr(grant, "is_active", False):
        return False
    if not getattr(grant, "is_approved", False):
        return False
    if not getattr(grant, "approved_by_user_id", None) or not getattr(grant, "approved_at", None):
        return False
    if not purpose or purpose not in (getattr(grant, "allowed_purposes", None) or []):
        return False

    user_id = getattr(user, "id", None)
    role_id = getattr(user, "role_id", None)
    department_id = getattr(user, "department_id", None)
    users = getattr(grant, "allowed_user_ids", None) or []
    roles = getattr(grant, "allowed_role_ids", None) or []
    departments = getattr(grant, "allowed_department_ids", None) or []

    if classification == "A":
        # A is public-corpus content, but still requires explicit wildcard
        # admission, approval, and purpose restriction.
        return "*" in users
    if classification == "C":
        # Restricted data requires a named-user grant; role-wide access is
        # intentionally insufficient.
        return bool(user_id and user_id in users)
    return bool(
        (user_id and user_id in users)
        or (role_id and role_id in roles)
        or (department_id and department_id in departments)
    )


def authorized_source_ids(
    db: Session,
    *,
    company_id: str,
    requester_id: str | None,
    agent_instance_id: str | None,
    purpose: str,
    task_id: str | None = None,
) -> tuple[set[str], set[str]]:
    """Return (knowledge_item_ids, knowledge_document_ids); fail closed."""
    if not requester_id or not agent_instance_id or not purpose:
        return set(), set()

    user = db.get(User, requester_id)
    agent = db.get(AgentInstance, agent_instance_id)
    if (
        user is None
        or user.status != "active"
        or user.company_id != company_id
        or agent is None
        or agent.status != "active"
        or agent.company_id != company_id
        or agent.company is None
        or not agent.company.is_active
        or (agent.subscription is not None and agent.subscription.status != "active")
    ):
        return set(), set()

    # Reuse the platform's trusted agent-access decision. Revoked agent access
    # therefore takes effect on the next retrieval.
    from app.services.access import require_agent_use
    from fastapi import HTTPException

    try:
        require_agent_use(
            db,
            user,
            company_id=company_id,
            agent_instance_id=agent_instance_id,
        )
    except HTTPException:
        return set(), set()

    grants = db.scalars(
        select(KnowledgeSourceGrant).where(
            KnowledgeSourceGrant.company_id == company_id,
        )
    ).all()

    item_versions = {}
    document_versions = {}
    item_candidates = {g.source_id for g in grants if g.source_type == "item"}
    document_candidates = {g.source_id for g in grants if g.source_type == "document"}
    if item_candidates:
        item_versions = {
            row.id: source_version_token(row.updated_at)
            for row in db.scalars(
                select(KnowledgeItem).where(
                    KnowledgeItem.company_id == company_id,
                    KnowledgeItem.id.in_(item_candidates),
                    KnowledgeItem.is_active.is_(True),
                )
            ).all()
        }
    if document_candidates:
        document_versions = {
            row.id: source_version_token(row.updated_at)
            for row in db.scalars(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.company_id == company_id,
                    KnowledgeDocument.id.in_(document_candidates),
                    KnowledgeDocument.status == DocumentStatus.READY,
                )
            ).all()
        }

    item_ids: set[str] = set()
    document_ids: set[str] = set()
    for grant in grants:
        reason = "audience_or_policy_denied"
        allowed = grant_allows(grant, user, purpose)
        if allowed and grant.source_type == "item":
            allowed = item_versions.get(grant.source_id) == grant.source_version
            reason = "source_version_changed_or_missing"
            if allowed:
                item_ids.add(grant.source_id)
        elif allowed and grant.source_type == "document":
            allowed = document_versions.get(grant.source_id) == grant.source_version
            reason = "source_not_ready_or_version_changed"
            if allowed:
                document_ids.add(grant.source_id)
        elif grant.source_type not in {"item", "document"}:
            allowed = False
            reason = "invalid_source_type"

        db.add(AuditLog(
            company_id=company_id,
            user_id=user.id,
            agent_instance_id=agent_instance_id,
            task_id=task_id,
            action="knowledge.retrieval.authorization",
            resource_type="knowledge_source",
            resource_id=grant.source_id,
            status="allowed" if allowed else "denied",
            details={
                "source_type": grant.source_type,
                "classification": grant.classification,
                "purpose": purpose,
                "policy_version": grant.policy_version,
                "reason": "authorized" if allowed else reason,
            },
        ))

    if not grants:
        db.add(AuditLog(
            company_id=company_id,
            user_id=user.id,
            agent_instance_id=agent_instance_id,
            task_id=task_id,
            action="knowledge.retrieval.authorization",
            resource_type="knowledge_retrieval",
            resource_id=None,
            status="denied",
            details={"purpose": purpose, "reason": "no_source_grants"},
        ))
    return item_ids, document_ids
