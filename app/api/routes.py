from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import AgentCatalog, AgentInstance, AgentSubscription, AuditLog, Company, KnowledgeItem, Task, User
from app.models.entities import TaskStatus
from app.schemas.domain import (
    AgentCatalogRead, AgentInstanceRead, AgentSubscriptionRead, AuditLogRead, CompanyCreate, CompanyRead,
    HireAgentRequest, KnowledgeCreate, KnowledgeRead, KnowledgeUpdate,
    TaskCreate, TaskRead, UserCreate, UserRead,
)
from app.services.audit import record_audit
from app.services.seed import get_or_create_role

router = APIRouter(prefix="/api/v1")


def get_company_or_404(db: Session, company_id: str) -> Company:
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


def get_current_user(x_user_id: str | None, db: Session) -> User:
    if not x_user_id:
        raise HTTPException(status_code=401, detail="X-User-ID header is required")
    user = db.get(User, x_user_id)
    if not user or user.status != "active":
        raise HTTPException(status_code=401, detail="Invalid or inactive user")
    return user


def require_company_user(db: Session, company_id: str, x_user_id: str | None) -> User:
    user = get_current_user(x_user_id, db)
    if user.company_id != company_id:
        raise HTTPException(status_code=403, detail="User does not belong to this company")
    return user


def require_permission(user: User, permission_key: str) -> None:
    permission_keys = {permission.key for permission in user.role.permissions}
    if permission_key not in permission_keys:
        raise HTTPException(status_code=403, detail=f"Permission denied: {permission_key}")


def get_owned_agent_or_404(db: Session, company_id: str, agent_instance_id: str) -> AgentInstance:
    agent = db.scalar(
        select(AgentInstance).where(
            AgentInstance.id == agent_instance_id,
            AgentInstance.company_id == company_id,
        )
    )
    if not agent:
        raise HTTPException(status_code=403, detail="Agent is not hired by this company")
    if agent.status != "active":
        raise HTTPException(status_code=409, detail="Agent subscription is not active")
    if agent.subscription.status != "active":
        raise HTTPException(status_code=409, detail="Agent subscription is not active")
    return agent


@router.post("/companies", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
def create_company(payload: CompanyCreate, db: Session = Depends(get_db)):
    company = Company(name=payload.name)
    db.add(company)
    db.flush()
    # Company creator is intentionally separated from user authentication for this local MVP.
    db.commit()
    db.refresh(company)
    return company


@router.post("/companies/{company_id}/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(company_id: str, payload: UserCreate, db: Session = Depends(get_db), x_user_id: str | None = Header(default=None)):
    company = get_company_or_404(db, company_id)
    if x_user_id:
        current = require_company_user(db, company_id, x_user_id)
        require_permission(current, "team.manage")

    role = get_or_create_role(db, payload.role)
    user = User(company_id=company.id, name=payload.name, email=payload.email, role_id=role.id)
    db.add(user)
    db.flush()
    record_audit(db, company_id=company.id, user_id=x_user_id, action="user.create", resource_type="user", resource_id=user.id, status="success")
    db.commit()
    db.refresh(user)
    return user


@router.get("/agent-catalog", response_model=list[AgentCatalogRead])
def list_agent_catalog(db: Session = Depends(get_db)):
    return list(db.scalars(select(AgentCatalog).where(AgentCatalog.status == "active")).all())


@router.post("/companies/{company_id}/agents/{catalog_agent_id}/hire", response_model=AgentInstanceRead, status_code=status.HTTP_201_CREATED)
def hire_agent(company_id: str, catalog_agent_id: str, payload: HireAgentRequest, db: Session = Depends(get_db), x_user_id: str | None = Header(default=None)):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.hire")
    catalog = db.get(AgentCatalog, catalog_agent_id)
    if not catalog or catalog.status != "active":
        raise HTTPException(status_code=404, detail="Agent catalog item not found or inactive")

    subscription = AgentSubscription(company_id=company_id, catalog_agent_id=catalog.id)
    db.add(subscription)
    db.flush()
    instance = AgentInstance(
        company_id=company_id,
        catalog_agent_id=catalog.id,
        subscription_id=subscription.id,
        name=payload.name,
        configuration={"role": catalog.role, "skills": catalog.skills, "allowed_tools": catalog.allowed_tools},
    )
    db.add(instance)
    db.flush()
    record_audit(db, company_id=company_id, user_id=user.id, agent_instance_id=instance.id, action="agent.hire", resource_type="agent_instance", resource_id=instance.id, status="success", details={"catalog_slug": catalog.slug, "subscription_id": subscription.id})
    db.commit()
    db.refresh(instance)
    return instance


@router.get("/companies/{company_id}/subscriptions", response_model=list[AgentSubscriptionRead])
def list_company_subscriptions(company_id: str, db: Session = Depends(get_db), x_user_id: str | None = Header(default=None)):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.read")
    return list(db.scalars(select(AgentSubscription).where(AgentSubscription.company_id == company_id)).all())


@router.post("/companies/{company_id}/subscriptions/{subscription_id}/cancel", response_model=AgentSubscriptionRead)
def cancel_subscription(company_id: str, subscription_id: str, db: Session = Depends(get_db), x_user_id: str | None = Header(default=None)):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.hire")
    subscription = db.scalar(select(AgentSubscription).where(AgentSubscription.id == subscription_id, AgentSubscription.company_id == company_id))
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    if subscription.status == "cancelled":
        return subscription
    subscription.status = "cancelled"
    subscription.cancelled_at = datetime.now(timezone.utc)
    instances = list(db.scalars(select(AgentInstance).where(AgentInstance.subscription_id == subscription.id)).all())
    for instance in instances:
        instance.status = "inactive"
    record_audit(db, company_id=company_id, user_id=user.id, action="agent.subscription.cancel", resource_type="agent_subscription", resource_id=subscription.id, status="success")
    db.commit()
    db.refresh(subscription)
    return subscription


@router.get("/companies/{company_id}/agents", response_model=list[AgentInstanceRead])
def list_company_agents(company_id: str, db: Session = Depends(get_db), x_user_id: str | None = Header(default=None)):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.read")
    return list(db.scalars(select(AgentInstance).where(AgentInstance.company_id == company_id)).all())


@router.post("/companies/{company_id}/knowledge", response_model=KnowledgeRead, status_code=status.HTTP_201_CREATED)
def create_knowledge(company_id: str, payload: KnowledgeCreate, db: Session = Depends(get_db), x_user_id: str | None = Header(default=None)):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "knowledge.write")
    if payload.agent_instance_id:
        get_owned_agent_or_404(db, company_id, payload.agent_instance_id)
    item = KnowledgeItem(company_id=company_id, **payload.model_dump())
    db.add(item)
    db.flush()
    record_audit(db, company_id=company_id, user_id=user.id, agent_instance_id=payload.agent_instance_id, action="knowledge.create", resource_type="knowledge", resource_id=item.id, status="success")
    db.commit()
    db.refresh(item)
    return item


@router.get("/companies/{company_id}/knowledge", response_model=list[KnowledgeRead])
def list_knowledge(company_id: str, db: Session = Depends(get_db), x_user_id: str | None = Header(default=None)):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "knowledge.read")
    return list(db.scalars(select(KnowledgeItem).where(KnowledgeItem.company_id == company_id)).all())


@router.patch("/companies/{company_id}/knowledge/{knowledge_id}", response_model=KnowledgeRead)
def update_knowledge(company_id: str, knowledge_id: str, payload: KnowledgeUpdate, db: Session = Depends(get_db), x_user_id: str | None = Header(default=None)):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "knowledge.write")
    item = db.scalar(select(KnowledgeItem).where(KnowledgeItem.id == knowledge_id, KnowledgeItem.company_id == company_id))
    if not item:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    record_audit(db, company_id=company_id, user_id=user.id, agent_instance_id=item.agent_instance_id, action="knowledge.update", resource_type="knowledge", resource_id=item.id, status="success")
    db.commit()
    db.refresh(item)
    return item


@router.delete("/companies/{company_id}/knowledge/{knowledge_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge(company_id: str, knowledge_id: str, db: Session = Depends(get_db), x_user_id: str | None = Header(default=None)):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "knowledge.write")
    item = db.scalar(select(KnowledgeItem).where(KnowledgeItem.id == knowledge_id, KnowledgeItem.company_id == company_id))
    if not item:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    record_audit(db, company_id=company_id, user_id=user.id, agent_instance_id=item.agent_instance_id, action="knowledge.delete", resource_type="knowledge", resource_id=item.id, status="success")
    db.delete(item)
    db.commit()


@router.post("/companies/{company_id}/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(company_id: str, payload: TaskCreate, db: Session = Depends(get_db), x_user_id: str | None = Header(default=None)):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "task.create")
    agent = get_owned_agent_or_404(db, company_id, payload.agent_instance_id)
    task = Task(company_id=company_id, **payload.model_dump(), status=TaskStatus.PENDING.value)
    db.add(task)
    db.flush()
    record_audit(db, company_id=company_id, user_id=user.id, agent_instance_id=agent.id, task_id=task.id, action="task.create", resource_type="task", resource_id=task.id, status="success")
    db.commit()
    db.refresh(task)
    return task


@router.get("/companies/{company_id}/tasks", response_model=list[TaskRead])
def list_tasks(company_id: str, db: Session = Depends(get_db), x_user_id: str | None = Header(default=None)):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "task.read")
    return list(db.scalars(select(Task).where(Task.company_id == company_id)).all())


@router.get("/companies/{company_id}/audit-logs", response_model=list[AuditLogRead])
def list_audit_logs(company_id: str, db: Session = Depends(get_db), x_user_id: str | None = Header(default=None)):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "audit.read")
    return list(db.scalars(select(AuditLog).where(AuditLog.company_id == company_id).order_by(AuditLog.created_at.desc())).all())
