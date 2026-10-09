"""Minimal, permission-scoped attribution for active Inbox records."""

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.api.routes import require_company_user, require_permission
from app.core.database import get_db
from app.models.entities import AgentInstance, Approval, AuditLog, DelegationRequest, Task, User

router = APIRouter(prefix="/api/v1/companies/{company_id}", tags=["inbox"])


class InboxAttributionRead(BaseModel):
    resource_id: str
    action: str
    actor_type: Literal["human", "agent", "unknown"]
    actor_name: str
    performed_at: datetime


@router.get("/inbox-attribution/{kind}", response_model=list[InboxAttributionRead])
def list_inbox_attribution(
    company_id: str,
    kind: Literal["task", "approval", "delegation"],
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    model, permission, resource_type, statuses = {
        "task": (Task, "task.read", "task", ["pending", "planning", "running", "waiting_approval", "failed"]),
        "approval": (Approval, "approval.read", "approval", ["pending"]),
        "delegation": (DelegationRequest, "agent.read", "delegation_request", ["pending", "accepted"]),
    }[kind]
    require_permission(user, permission)
    active_ids = select(model.id).where(model.company_id == company_id, model.status.in_(statuses))
    # Rank in SQL so only the newest event per visible resource leaves the database.
    latest = select(
        AuditLog.resource_id, AuditLog.action, AuditLog.user_id,
        AuditLog.agent_instance_id, AuditLog.created_at,
        func.row_number().over(
            partition_by=AuditLog.resource_id,
            order_by=(AuditLog.created_at.desc(), AuditLog.id.desc()),
        ).label("rank"),
    ).where(
        AuditLog.company_id == company_id,
        AuditLog.resource_type == resource_type,
        AuditLog.resource_id.in_(active_ids),
    ).subquery()
    rows = db.execute(select(latest, User.name.label("human_name"), AgentInstance.name.label("agent_name"))
        .outerjoin(User, and_(User.id == latest.c.user_id, User.company_id == company_id))
        .outerjoin(AgentInstance, and_(AgentInstance.id == latest.c.agent_instance_id, AgentInstance.company_id == company_id))
        .where(latest.c.rank == 1)).mappings()
    result = []
    for row in rows:
        if row["user_id"]:
            actor_type, actor_name = "human", row["human_name"] or "User (name unavailable)"
        elif row["agent_instance_id"]:
            actor_type, actor_name = "agent", row["agent_name"] or "AI agent (name unavailable)"
        else:
            actor_type, actor_name = "unknown", "Actor not recorded"
        timestamp = row["created_at"]
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        result.append(InboxAttributionRead(
            resource_id=row["resource_id"], action=row["action"],
            actor_type=actor_type, actor_name=actor_name,
            performed_at=timestamp.astimezone(timezone.utc),
        ))
    return result
