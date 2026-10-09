"""Phase 3 — per-agent human access checks."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AgentAccess, User


def user_permission_keys(user: User) -> set[str]:
    if user.role is None:
        return set()
    return {p.key for p in (user.role.permissions or [])}


def is_company_admin(user: User) -> bool:
    """Owner/manager with broad agent.manage may administer all agents."""
    keys = user_permission_keys(user)
    return "agent.manage" in keys or "agent.hire" in keys and user.role and user.role.name in {
        "owner",
        "manager",
    }


def get_agent_access(
    db: Session,
    *,
    company_id: str,
    agent_instance_id: str,
    user_id: str,
) -> AgentAccess | None:
    return db.scalar(
        select(AgentAccess).where(
            AgentAccess.company_id == company_id,
            AgentAccess.agent_instance_id == agent_instance_id,
            AgentAccess.user_id == user_id,
        )
    )


def require_agent_use(
    db: Session,
    user: User,
    *,
    company_id: str,
    agent_instance_id: str,
) -> None:
    """User must have can_use on the agent, or be company admin."""
    if user.company_id != company_id or user.status != "active" or user.company is None or not user.company.is_active:
        raise HTTPException(status_code=403, detail="User is not active in this company")
    if is_company_admin(user):
        return
    access = get_agent_access(
        db,
        company_id=company_id,
        agent_instance_id=agent_instance_id,
        user_id=user.id,
    )
    if access and access.can_use:
        return
    raise HTTPException(
        status_code=403,
        detail="You are not allowed to use this AI Employee",
    )


def require_agent_manage(
    db: Session,
    user: User,
    *,
    company_id: str,
    agent_instance_id: str,
) -> None:
    """User must have can_manage on the agent, or company-level agent.manage."""
    keys = user_permission_keys(user)
    if "agent.manage" in keys:
        return
    access = get_agent_access(
        db,
        company_id=company_id,
        agent_instance_id=agent_instance_id,
        user_id=user.id,
    )
    if access and access.can_manage:
        return
    raise HTTPException(
        status_code=403,
        detail="You are not allowed to configure this AI Employee",
    )


def require_agent_approve(
    db: Session,
    user: User,
    *,
    company_id: str,
    agent_instance_id: str,
) -> None:
    """User must have can_approve on the agent, or company-level approval.manage."""
    keys = user_permission_keys(user)
    if "approval.manage" in keys:
        return
    access = get_agent_access(
        db,
        company_id=company_id,
        agent_instance_id=agent_instance_id,
        user_id=user.id,
    )
    if access and access.can_approve:
        return
    raise HTTPException(
        status_code=403,
        detail="You are not allowed to approve actions for this AI Employee",
    )


def grant_access(
    db: Session,
    *,
    company_id: str,
    agent_instance_id: str,
    user_id: str,
    can_use: bool = True,
    can_manage: bool = False,
    can_approve: bool = False,
    is_supervisor: bool = False,
) -> AgentAccess:
    existing = get_agent_access(
        db,
        company_id=company_id,
        agent_instance_id=agent_instance_id,
        user_id=user_id,
    )
    if existing:
        existing.can_use = can_use
        existing.can_manage = can_manage
        existing.can_approve = can_approve
        existing.is_supervisor = is_supervisor
        db.flush()
        return existing

    access = AgentAccess(
        company_id=company_id,
        agent_instance_id=agent_instance_id,
        user_id=user_id,
        can_use=can_use,
        can_manage=can_manage,
        can_approve=can_approve,
        is_supervisor=is_supervisor,
    )
    db.add(access)
    db.flush()
    return access


def require_execution_actor(db: Session, *, company_id: str, agent_instance_id: str, user_id: str | None) -> None:
    """Human-triggered orchestration uses the same access check as direct requests."""
    if user_id is None:
        return  # Trusted scheduler/service callers still pass runtime tenant/scope checks.
    user = db.scalar(select(User).where(User.id == user_id, User.company_id == company_id))
    if user is None:
        raise ValueError("Execution actor not found in this company.")
    require_agent_use(db, user, company_id=company_id, agent_instance_id=agent_instance_id)
