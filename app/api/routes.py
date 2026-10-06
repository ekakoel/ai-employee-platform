from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.knowledge.service import save_document
from app.models import (
    AgentCatalog,
    AgentInstance,
    AgentSubscription,
    Approval,
    AuditLog,
    Company,
    KnowledgeItem,
    Task,
    User,
)
from app.models.entities import TaskStatus
from app.runtime.tool_executor import ToolExecutionError, ToolExecutor
from app.schemas.domain import (
    AgentCatalogRead,
    AgentInstanceRead,
    AgentSubscriptionRead,
    ApprovalRead,
    ApprovalReviewRequest,
    AuditLogRead,
    CompanyCreate,
    CompanyRead,
    HireAgentRequest,
    KnowledgeCreate,
    KnowledgeDocumentRead,
    KnowledgeRead,
    KnowledgeUpdate,
    TaskCreate,
    TaskRead,
    UserCreate,
    UserRead,
)
from app.services.approval import ApprovalService
from app.services.audit import record_audit
from app.services.seed import get_or_create_role
from app.services.task_runtime import TaskRuntimeService

router = APIRouter(prefix="/api/v1")


def get_company_or_404(db: Session, company_id: str) -> Company:
    company = db.get(Company, company_id)

    if not company:
        raise HTTPException(
            status_code=404,
            detail="Company not found",
        )

    return company


def get_current_user(
    x_user_id: str | None,
    db: Session,
) -> User:
    if not x_user_id:
        raise HTTPException(
            status_code=401,
            detail="X-User-ID header is required",
        )

    user = db.get(User, x_user_id)

    if not user or user.status != "active":
        raise HTTPException(
            status_code=401,
            detail="Invalid or inactive user",
        )

    return user


def require_company_user(
    db: Session,
    company_id: str,
    x_user_id: str | None,
) -> User:
    user = get_current_user(x_user_id, db)

    if user.company_id != company_id:
        raise HTTPException(
            status_code=403,
            detail="User does not belong to this company",
        )

    return user


def require_permission(
    user: User,
    permission_key: str,
) -> None:
    permission_keys = {
        permission.key
        for permission in user.role.permissions
    }

    if permission_key not in permission_keys:
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied: {permission_key}",
        )


def get_owned_agent_or_404(
    db: Session,
    company_id: str,
    agent_instance_id: str,
) -> AgentInstance:
    agent = db.scalar(
        select(AgentInstance).where(
            AgentInstance.id == agent_instance_id,
            AgentInstance.company_id == company_id,
        )
    )

    if not agent:
        raise HTTPException(
            status_code=403,
            detail="Agent is not hired by this company",
        )

    if agent.status != "active":
        raise HTTPException(
            status_code=409,
            detail="Agent subscription is not active",
        )

    if agent.subscription.status != "active":
        raise HTTPException(
            status_code=409,
            detail="Agent subscription is not active",
        )

    return agent


@router.post(
    "/companies",
    response_model=CompanyRead,
    status_code=status.HTTP_201_CREATED,
)
def create_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
):
    existing_company = db.scalar(
        select(Company).where(
            Company.name == payload.name
        )
    )

    if existing_company:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Company '{payload.name}' already exists.",
        )

    company = Company(
        name=payload.name,
    )

    db.add(company)

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Company '{payload.name}' already exists.",
        ) from exc

    # Company creator is intentionally separated from
    # user authentication for this local MVP.
    db.commit()
    db.refresh(company)

    return company


@router.post(
    "/companies/{company_id}/agents/{agent_instance_id}/tools/{tool_name}/execute",
)
def execute_agent_tool(
    company_id: str,
    agent_instance_id: str,
    tool_name: str,
    payload: dict,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(
        db,
        company_id,
        x_user_id,
    )

    require_permission(
        user,
        "task.create",
    )

    arguments = payload.get("arguments", {})
    task_id = payload.get("task_id")

    executor = ToolExecutor(db)

    try:
        return executor.execute(
            company_id=company_id,
            agent_instance_id=agent_instance_id,
            tool_name=tool_name,
            arguments=arguments,
            task_id=task_id,
        )

    except ToolExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.post(
    "/companies/{company_id}/users",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    company_id: str,
    payload: UserCreate,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    company = get_company_or_404(
        db,
        company_id,
    )

    if x_user_id:
        current = require_company_user(
            db,
            company_id,
            x_user_id,
        )

        require_permission(
            current,
            "team.manage",
        )

    role = get_or_create_role(
        db,
        payload.role,
    )

    user = User(
        company_id=company.id,
        name=payload.name,
        email=payload.email,
        role_id=role.id,
    )

    db.add(user)
    db.flush()

    record_audit(
        db,
        company_id=company.id,
        user_id=x_user_id,
        action="user.create",
        resource_type="user",
        resource_id=user.id,
        status="success",
    )

    db.commit()
    db.refresh(user)

    return user


@router.get(
    "/agent-catalog",
    response_model=list[AgentCatalogRead],
)
def list_agent_catalog(
    db: Session = Depends(get_db),
):
    return list(
        db.scalars(
            select(AgentCatalog).where(
                AgentCatalog.status == "active"
            )
        ).all()
    )


@router.post(
    "/companies/{company_id}/agents/{catalog_agent_id}/hire",
    response_model=AgentInstanceRead,
    status_code=status.HTTP_201_CREATED,
)
def hire_agent(
    company_id: str,
    catalog_agent_id: str,
    payload: HireAgentRequest,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(
        db,
        company_id,
        x_user_id,
    )

    require_permission(
        user,
        "agent.hire",
    )

    catalog = db.get(
        AgentCatalog,
        catalog_agent_id,
    )

    if not catalog or catalog.status != "active":
        raise HTTPException(
            status_code=404,
            detail="Agent catalog item not found or inactive",
        )

    subscription = AgentSubscription(
        company_id=company_id,
        catalog_agent_id=catalog.id,
    )

    db.add(subscription)
    db.flush()

    instance = AgentInstance(
        company_id=company_id,
        catalog_agent_id=catalog.id,
        subscription_id=subscription.id,
        name=payload.name,
        configuration={
            "role": catalog.role,
            "skills": catalog.skills,
            "allowed_tools": catalog.allowed_tools,
        },
    )

    db.add(instance)
    db.flush()

    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        agent_instance_id=instance.id,
        action="agent.hire",
        resource_type="agent_instance",
        resource_id=instance.id,
        status="success",
        details={
            "catalog_slug": catalog.slug,
            "subscription_id": subscription.id,
        },
    )

    db.commit()
    db.refresh(instance)

    return instance


@router.get(
    "/companies/{company_id}/subscriptions",
    response_model=list[AgentSubscriptionRead],
)
def list_company_subscriptions(
    company_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(
        db,
        company_id,
        x_user_id,
    )

    require_permission(
        user,
        "agent.read",
    )

    return list(
        db.scalars(
            select(AgentSubscription).where(
                AgentSubscription.company_id == company_id
            )
        ).all()
    )


@router.post(
    "/companies/{company_id}/subscriptions/{subscription_id}/cancel",
    response_model=AgentSubscriptionRead,
)
def cancel_subscription(
    company_id: str,
    subscription_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(
        db,
        company_id,
        x_user_id,
    )

    require_permission(
        user,
        "agent.hire",
    )

    subscription = db.scalar(
        select(AgentSubscription).where(
            AgentSubscription.id == subscription_id,
            AgentSubscription.company_id == company_id,
        )
    )

    if not subscription:
        raise HTTPException(
            status_code=404,
            detail="Subscription not found",
        )

    if subscription.status == "cancelled":
        return subscription

    subscription.status = "cancelled"
    subscription.cancelled_at = datetime.now(timezone.utc)

    instances = list(
        db.scalars(
            select(AgentInstance).where(
                AgentInstance.subscription_id == subscription.id
            )
        ).all()
    )

    for instance in instances:
        instance.status = "inactive"

    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        action="agent.subscription.cancel",
        resource_type="agent_subscription",
        resource_id=subscription.id,
        status="success",
    )

    db.commit()
    db.refresh(subscription)

    return subscription


@router.get(
    "/companies/{company_id}/agents",
    response_model=list[AgentInstanceRead],
)
def list_company_agents(
    company_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(
        db,
        company_id,
        x_user_id,
    )

    require_permission(
        user,
        "agent.read",
    )

    return list(
        db.scalars(
            select(AgentInstance).where(
                AgentInstance.company_id == company_id
            )
        ).all()
    )


@router.post(
    "/companies/{company_id}/knowledge",
    response_model=KnowledgeRead,
    status_code=status.HTTP_201_CREATED,
)
def create_knowledge(
    company_id: str,
    payload: KnowledgeCreate,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(
        db,
        company_id,
        x_user_id,
    )

    require_permission(
        user,
        "knowledge.write",
    )

    if payload.agent_instance_id:
        get_owned_agent_or_404(
            db,
            company_id,
            payload.agent_instance_id,
        )

    item = KnowledgeItem(
        company_id=company_id,
        **payload.model_dump(),
    )

    db.add(item)
    db.flush()

    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        agent_instance_id=payload.agent_instance_id,
        action="knowledge.create",
        resource_type="knowledge",
        resource_id=item.id,
        status="success",
    )

    db.commit()
    db.refresh(item)

    return item


@router.post(
    "/companies/{company_id}/agents/{agent_instance_id}/knowledge",
    response_model=KnowledgeRead,
    status_code=status.HTTP_201_CREATED,
)
def create_agent_knowledge(
    company_id: str,
    agent_instance_id: str,
    payload: KnowledgeCreate,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(
        db,
        company_id,
        x_user_id,
    )

    require_permission(
        user,
        "knowledge.write",
    )

    agent = get_owned_agent_or_404(
        db,
        company_id,
        agent_instance_id,
    )

    item = KnowledgeItem(
        company_id=company_id,
        agent_instance_id=agent.id,
        title=payload.title,
        content=payload.content,
        category=payload.category,
    )

    db.add(item)
    db.flush()

    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        agent_instance_id=agent.id,
        action="knowledge.create",
        resource_type="knowledge",
        resource_id=item.id,
        status="success",
        details={
            "scope": "agent",
            "category": item.category,
        },
    )

    db.commit()
    db.refresh(item)

    return item


@router.get(
    "/companies/{company_id}/knowledge",
    response_model=list[KnowledgeRead],
)
def list_knowledge(
    company_id: str,
    agent_instance_id: str | None = None,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(
        db,
        company_id,
        x_user_id,
    )

    require_permission(
        user,
        "knowledge.read",
    )

    query = select(KnowledgeItem).where(
        KnowledgeItem.company_id == company_id
    )

    if agent_instance_id:
        get_owned_agent_or_404(
            db,
            company_id,
            agent_instance_id,
        )

        query = query.where(
            (KnowledgeItem.agent_instance_id.is_(None))
            | (KnowledgeItem.agent_instance_id == agent_instance_id)
        )

    return list(
        db.scalars(query).all()
    )


@router.patch(
    "/companies/{company_id}/knowledge/{knowledge_id}",
    response_model=KnowledgeRead,
)
def update_knowledge(
    company_id: str,
    knowledge_id: str,
    payload: KnowledgeUpdate,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(
        db,
        company_id,
        x_user_id,
    )

    require_permission(
        user,
        "knowledge.write",
    )

    item = db.scalar(
        select(KnowledgeItem).where(
            KnowledgeItem.id == knowledge_id,
            KnowledgeItem.company_id == company_id,
        )
    )

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Knowledge item not found",
        )

    for key, value in payload.model_dump(
        exclude_unset=True
    ).items():
        setattr(item, key, value)

    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        agent_instance_id=item.agent_instance_id,
        action="knowledge.update",
        resource_type="knowledge",
        resource_id=item.id,
        status="success",
    )

    db.commit()
    db.refresh(item)

    return item


@router.delete(
    "/companies/{company_id}/knowledge/{knowledge_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_knowledge(
    company_id: str,
    knowledge_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(
        db,
        company_id,
        x_user_id,
    )

    require_permission(
        user,
        "knowledge.write",
    )

    item = db.scalar(
        select(KnowledgeItem).where(
            KnowledgeItem.id == knowledge_id,
            KnowledgeItem.company_id == company_id,
        )
    )

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Knowledge item not found",
        )

    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        agent_instance_id=item.agent_instance_id,
        action="knowledge.delete",
        resource_type="knowledge",
        resource_id=item.id,
        status="success",
    )

    db.delete(item)
    db.commit()


@router.post(
    "/companies/{company_id}/tasks",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
)
def create_task(
    company_id: str,
    payload: TaskCreate,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(
        db,
        company_id,
        x_user_id,
    )

    require_permission(
        user,
        "task.create",
    )

    agent = get_owned_agent_or_404(
        db,
        company_id,
        payload.agent_instance_id,
    )

    task = Task(
        company_id=company_id,
        **payload.model_dump(),
        status=TaskStatus.PENDING.value,
    )

    db.add(task)
    db.flush()

    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        agent_instance_id=agent.id,
        task_id=task.id,
        action="task.create",
        resource_type="task",
        resource_id=task.id,
        status="success",
    )

    db.commit()
    db.refresh(task)

    return task


@router.get(
    "/companies/{company_id}/tasks",
    response_model=list[TaskRead],
)
def list_tasks(
    company_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(
        db,
        company_id,
        x_user_id,
    )

    require_permission(
        user,
        "task.read",
    )

    return list(
        db.scalars(
            select(Task).where(
                Task.company_id == company_id
            )
        ).all()
    )


@router.post(
    "/companies/{company_id}/tasks/{task_id}/execute",
    response_model=TaskRead,
)
def execute_task(
    company_id: str,
    task_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(
        db,
        company_id,
        x_user_id,
    )

    require_permission(
        user,
        "task.create",
    )

    runtime = TaskRuntimeService()

    try:
        return runtime.execute(
            db,
            company_id=company_id,
            task_id=task_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/companies/{company_id}/tasks/{task_id}/execute-llm",
    response_model=TaskRead,
)
def execute_task_llm(
    company_id: str,
    task_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(
        db,
        company_id,
        x_user_id,
    )

    require_permission(
        user,
        "task.create",
    )

    runtime = TaskRuntimeService()

    try:
        return runtime.execute_with_llm(
            db,
            company_id=company_id,
            task_id=task_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/companies/{company_id}/approvals",
    response_model=list[ApprovalRead],
)
def list_company_approvals(
    company_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(
        db,
        company_id,
        x_user_id,
    )

    require_permission(
        user,
        "approval.read",
    )

    return list(
        db.scalars(
            select(Approval)
            .where(
                Approval.company_id == company_id
            )
            .order_by(
                Approval.created_at.desc()
            )
        ).all()
    )


@router.post(
    "/companies/{company_id}/approvals/{approval_id}/approve",
    response_model=ApprovalRead,
)
def approve_company_approval(
    company_id: str,
    approval_id: str,
    payload: ApprovalReviewRequest,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(
        db,
        company_id,
        x_user_id,
    )

    require_permission(
        user,
        "approval.manage",
    )

    service = ApprovalService(db)

    try:
        approval = service.approve(
            approval_id=approval_id,
            company_id=company_id,
            user_id=user.id,
            comment=payload.comment,
        )

        runtime = TaskRuntimeService()

        runtime.resume_after_approval(
            db,
            company_id=company_id,
            task_id=approval.task_id,
            approval_id=approval.id,
        )

        db.refresh(approval)

        return approval

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/companies/{company_id}/approvals/{approval_id}/reject",
    response_model=ApprovalRead,
)
def reject_company_approval(
    company_id: str,
    approval_id: str,
    payload: ApprovalReviewRequest,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(
        db,
        company_id,
        x_user_id,
    )

    require_permission(
        user,
        "approval.manage",
    )

    service = ApprovalService(db)

    try:
        approval = service.reject(
            approval_id=approval_id,
            company_id=company_id,
            user_id=user.id,
            comment=payload.comment,
        )

        runtime = TaskRuntimeService()

        runtime.reject_after_approval(
            db,
            company_id=company_id,
            task_id=approval.task_id,
            approval_id=approval.id,
            reason=payload.comment,
        )

        db.refresh(approval)

        return approval

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/companies/{company_id}/audit-logs",
    response_model=list[AuditLogRead],
)
def list_audit_logs(
    company_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(
        db,
        company_id,
        x_user_id,
    )

    require_permission(
        user,
        "audit.read",
    )

    return list(
        db.scalars(
            select(AuditLog)
            .where(
                AuditLog.company_id == company_id
            )
            .order_by(
                AuditLog.created_at.desc()
            )
        ).all()
    )


@router.post(
    "/companies/{company_id}/knowledge/documents",
    response_model=KnowledgeDocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_knowledge_document(
    company_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(
        db,
        company_id,
        x_user_id,
    )

    require_permission(
        user,
        "knowledge.write",
    )

    data = await file.read()

    if not data:
        raise HTTPException(
            status_code=400,
            detail="Uploaded document is empty",
        )

    document = save_document(
        db,
        company_id=company_id,
        agent_instance_id=None,
        original_filename=file.filename or "document",
        content_type=file.content_type or "application/octet-stream",
        data=data,
    )

    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        agent_instance_id=None,
        action="knowledge.document.create",
        resource_type="knowledge_document",
        resource_id=document.id,
        status="success",
        details={
            "filename": document.original_filename,
            "status": (
                document.status.value
                if hasattr(document.status, "value")
                else str(document.status)
            ),
        },
    )

    db.commit()
    db.refresh(document)

    return document


@router.post(
    "/companies/{company_id}/agents/{agent_instance_id}/knowledge/documents",
    response_model=KnowledgeDocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_agent_knowledge_document(
    company_id: str,
    agent_instance_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(
        db,
        company_id,
        x_user_id,
    )

    require_permission(
        user,
        "knowledge.write",
    )

    agent = get_owned_agent_or_404(
        db,
        company_id,
        agent_instance_id,
    )

    data = await file.read()

    if not data:
        raise HTTPException(
            status_code=400,
            detail="Uploaded document is empty",
        )

    document = save_document(
        db,
        company_id=company_id,
        agent_instance_id=agent.id,
        original_filename=file.filename or "document",
        content_type=file.content_type or "application/octet-stream",
        data=data,
    )

    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        agent_instance_id=agent.id,
        action="knowledge.document.create",
        resource_type="knowledge_document",
        resource_id=document.id,
        status="success",
        details={
            "filename": document.original_filename,
            "status": (
                document.status.value
                if hasattr(document.status, "value")
                else str(document.status)
            ),
        },
    )

    db.commit()
    db.refresh(document)

    return document
