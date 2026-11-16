"""Fail-closed authorization for knowledge source retrieval.

A chunk is readable only when its parent source has an active, approved grant
that matches the authenticated requester, agent, and declared purpose.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    AgentInstance,
    KnowledgeSourceGrant,
    User,
)


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
            KnowledgeSourceGrant.is_active.is_(True),
            KnowledgeSourceGrant.is_approved.is_(True),
        )
    ).all()

    item_ids: set[str] = set()
    document_ids: set[str] = set()
    for grant in grants:
        if not grant_allows(grant, user, purpose):
            continue
        if grant.source_type == "item":
            item_ids.add(grant.source_id)
        elif grant.source_type == "document":
            document_ids.add(grant.source_id)
    return item_ids, document_ids
