from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.knowledge.service import save_document
from app.knowledge.indexing import replace_chunks_for_item, replace_chunks_for_document
from app.knowledge.retrieval import (
    active_agent_memories,
    search_knowledge_chunks,
    search_knowledge_items,
)
from app.models import (
    Department,
    AgentTeam,
    AgentTeamMember,
    AgentAccess,
    AgentCatalog,
    AgentInstance,
    AgentMemory,
    AgentSkill,
    AgentSubscription,
    Approval,
    AuditLog,
    AutomationRule,
    AutomationRun,
    Company,
    DelegationRequest,
    Experience,
    KnowledgeChunk,
    KnowledgeItem,
    Policy,
    Skill,
    Task,
    User,
)
from app.models.entities import TaskStatus
from app.runtime.tool_executor import ToolExecutionError, ToolExecutor
from app.schemas.domain import (
    ConversationCreate,
    ConversationRead,
    MessageCreate,
    MessageRead,
    ChatPostResponse,
    AgentAccessCreate,
    AgentAccessRead,
    AgentAccessUpdate,
    AgentSkillAssign,
    AgentSkillRead,
    SkillCreate,
    SkillRead,
    PolicyCreate,
    DepartmentCreate,
    DepartmentUpdate,
    DepartmentRead,
    AgentTeamCreate,
    AgentTeamUpdate,
    AgentTeamRead,
    AgentTeamAddMembers,
    PolicySimulateRequest,
    PolicyRead,
    PolicyUpdate,
    AgentMemoryCreate,
    AgentMemoryRead,
    AgentMemoryUpdate,
    ExperienceCreate,
    AgentDirectoryEntry,
    TargetValidationRequest,
    TargetValidationResult,
    DelegationRequestCreate,
    DelegationRequestRead,
    DelegationExecuteRequest,
    ExperienceFromTaskRequest,
    ExperienceRead,
    ExperienceSearchHit,
    ExperienceSearchRequest,
    ExperienceValidateRequest,
    ExperienceFeedbackRequest,
    AutomationRuleCreate,
    AutomationRuleRead,
    AutomationRunRead,
    AutomationEventRequest,
    KnowledgeSearchRequest,
    KnowledgeSearchHit,
    AgentCatalogRead,
    AgentInstanceRead,
    AgentInstanceUpdate,
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
from app.services.skills import (
    assign_skill,
    get_skill_for_company,
    list_agent_skills,
    list_available_skills,
)
from app.services.scope_guard import check_scope, enforce_scope_on_task
from app.security.policy_engine import get_policy_engine
from app.services.governance import (
    agent_performance,
    approval_metrics,
    audit_analytics,
    company_overview,
    experience_quality,
)
from app.services.automation import (
    fire_event,
    retry_run,
    tick_schedules,
)
from app.services.access import (
    grant_access,
    require_agent_approve,
    require_agent_manage,
    require_agent_use,
)
from app.services.approval import ApprovalService
from app.services.consultation import run_consultation
from app.services.delegation import (
    accept_delegation,
    cancel_delegation,
    execute_delegation,
    mark_timeout_if_needed,
    propagate_child_task_result,
    reject_delegation,
)
from app.services.directory import (
    discover_agents,
    list_directory,
    validate_delegation_target,
)
from app.services.experience import (
    archive_experience,
    create_candidate_from_task,
    get_experience_for_company,
    record_successful_reuse,
    search_validated_experiences,
    submit_feedback,
    validate_experience,
)
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
    authorization: str | None = None,
) -> User:
    from app.core.auth import resolve_user_id

    user_id = resolve_user_id(authorization=authorization, x_user_id=x_user_id)
    user = db.get(User, user_id)
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
    authorization: str | None = None,
) -> User:
    user = get_current_user(x_user_id, db, authorization=authorization)

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
        from app.services.quotas import get_or_assign_plan
        get_or_assign_plan(db, company.id)
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

    existing_users = db.scalar(
        select(User.id).where(User.company_id == company_id).limit(1)
    )
    # First user for a company is bootstrap (Quick start / open setup).
    # Later users require team.manage from a valid company member.
    if existing_users is not None:
        if not x_user_id:
            raise HTTPException(
                status_code=401,
                detail="Authentication required to add users",
            )
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

    password_hash = None
    if getattr(payload, "password", None):
        from app.core.passwords import hash_password

        try:
            password_hash = hash_password(payload.password)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    department_id = getattr(payload, "department_id", None)
    if department_id:
        dept = db.scalar(
            select(Department).where(
                Department.id == department_id,
                Department.company_id == company.id,
            )
        )
        if not dept:
            raise HTTPException(status_code=400, detail="Department not found in company")

    user = User(
        company_id=company.id,
        name=payload.name,
        email=payload.email,
        role_id=role.id,
        password_hash=password_hash,
        department_id=department_id,
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
                AgentCatalog.status == "active",
                AgentCatalog.is_published.is_(True),
            )
        ).all()
    )


@router.get(
    "/agent-catalog/{catalog_id}",
    response_model=AgentCatalogRead,
)
def get_agent_catalog(
    catalog_id: str,
    db: Session = Depends(get_db),
):
    catalog = db.get(AgentCatalog, catalog_id)
    if not catalog or catalog.status != "active" or not catalog.is_published:
        raise HTTPException(
            status_code=404,
            detail="Agent catalog item not found or inactive",
        )
    return catalog


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

    from app.services.quotas import enforce_agent_quota
    enforce_agent_quota(db, company_id)

    catalog = db.get(
        AgentCatalog,
        catalog_agent_id,
    )

    if (
        not catalog
        or catalog.status != "active"
        or not catalog.is_published
    ):
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

    # Snapshot template defaults onto the instance at hire time.
    skills = list(catalog.skills or [])
    allowed_tools = list(catalog.allowed_tools or [])
    scope = list(catalog.scope or [])
    policies = dict(catalog.default_policies or {})

    instance = AgentInstance(
        company_id=company_id,
        catalog_agent_id=catalog.id,
        subscription_id=subscription.id,
        name=payload.name,
        template_version=catalog.version,
        instructions=catalog.default_instructions or "",
        skills=skills,
        allowed_tools=allowed_tools,
        scope=scope,
        autonomy=catalog.default_autonomy or "1",
        policies=policies,
        configuration={
            "role": catalog.role,
            "skills": skills,
            "allowed_tools": allowed_tools,
            "evaluation_criteria": list(catalog.evaluation_criteria or []),
            "knowledge_requirements": list(
                catalog.default_knowledge_requirements or []
            ),
            "approval_recommendations": dict(
                catalog.default_approval_recommendations or {}
            ),
        },
    )

    instance.supervisor_user_id = user.id
    db.add(instance)
    db.flush()

    # Phase 3: hiring user becomes supervisor with full access
    grant_access(
        db,
        company_id=company_id,
        agent_instance_id=instance.id,
        user_id=user.id,
        can_use=True,
        can_manage=True,
        can_approve=True,
        is_supervisor=True,
    )

    # Phase 4: auto-assign platform/company skills matching template skill keys
    for skill_key in list(catalog.skills or []):
        skill = db.scalar(
            select(Skill).where(
                Skill.slug == skill_key,
                Skill.is_active.is_(True),
                or_(
                    Skill.company_id.is_(None),
                    Skill.company_id == company_id,
                ),
            )
        )
        if skill:
            assign_skill(
                db,
                company_id=company_id,
                agent_instance_id=instance.id,
                skill_id=skill.id,
            )

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
            "template_version": catalog.version,
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
    department_id: str | None = None,
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

    q = select(AgentInstance).where(AgentInstance.company_id == company_id)
    if department_id:
        q = q.where(AgentInstance.department_id == department_id)

    return list(db.scalars(q).all())


@router.patch(
    "/companies/{company_id}/agents/{agent_instance_id}",
    response_model=AgentInstanceRead,
)
def update_company_agent(
    company_id: str,
    agent_instance_id: str,
    payload: AgentInstanceUpdate,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    """Company customization of a hired Agent Instance."""
    user = require_company_user(
        db,
        company_id,
        x_user_id,
    )

    instance = db.scalar(
        select(AgentInstance).where(
            AgentInstance.id == agent_instance_id,
            AgentInstance.company_id == company_id,
        )
    )
    if not instance:
        raise HTTPException(
            status_code=404,
            detail="Agent is not hired by this company",
        )

    require_agent_manage(
        db,
        user,
        company_id=company_id,
        agent_instance_id=instance.id,
    )

    if payload.name is not None:
        instance.name = payload.name
    if payload.instructions is not None:
        instance.instructions = payload.instructions
    if payload.autonomy is not None:
        instance.autonomy = payload.autonomy
    if payload.policies is not None:
        instance.policies = dict(payload.policies)
    if payload.department_id is not None:
        if payload.department_id == "":
            instance.department_id = None
        else:
            dept = db.scalar(
                select(Department).where(
                    Department.id == payload.department_id,
                    Department.company_id == company_id,
                )
            )
            if not dept:
                raise HTTPException(
                    status_code=400,
                    detail="Department not found in company",
                )
            instance.department_id = payload.department_id
    if payload.supervisor_user_id is not None:
        instance.supervisor_user_id = payload.supervisor_user_id or None

    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        agent_instance_id=instance.id,
        action="agent.update",
        resource_type="agent_instance",
        resource_id=instance.id,
        status="success",
        details={
            "fields": [
                key
                for key, value in payload.model_dump(exclude_unset=True).items()
                if value is not None
            ],
        },
    )

    db.commit()
    db.refresh(instance)
    return instance


@router.get(
    "/companies/{company_id}/agents/{agent_instance_id}/access",
    response_model=list[AgentAccessRead],
)
def list_agent_access(
    company_id: str,
    agent_instance_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    get_owned_agent_or_404(db, company_id, agent_instance_id)
    require_agent_manage(
        db, user, company_id=company_id, agent_instance_id=agent_instance_id
    )
    return list(
        db.scalars(
            select(AgentAccess).where(
                AgentAccess.company_id == company_id,
                AgentAccess.agent_instance_id == agent_instance_id,
            )
        ).all()
    )


@router.post(
    "/companies/{company_id}/agents/{agent_instance_id}/access",
    response_model=AgentAccessRead,
    status_code=status.HTTP_201_CREATED,
)
def assign_agent_access(
    company_id: str,
    agent_instance_id: str,
    payload: AgentAccessCreate,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    agent = get_owned_agent_or_404(db, company_id, agent_instance_id)
    require_agent_manage(
        db, user, company_id=company_id, agent_instance_id=agent_instance_id
    )

    target = db.scalar(
        select(User).where(
            User.id == payload.user_id,
            User.company_id == company_id,
        )
    )
    if not target:
        raise HTTPException(status_code=404, detail="User not found in this company")

    access = grant_access(
        db,
        company_id=company_id,
        agent_instance_id=agent.id,
        user_id=target.id,
        can_use=payload.can_use,
        can_manage=payload.can_manage,
        can_approve=payload.can_approve,
        is_supervisor=payload.is_supervisor,
    )

    if payload.is_supervisor:
        agent.supervisor_user_id = target.id

    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        agent_instance_id=agent.id,
        action="agent.access.assign",
        resource_type="agent_access",
        resource_id=access.id,
        status="success",
        details={
            "target_user_id": target.id,
            "can_use": payload.can_use,
            "can_manage": payload.can_manage,
            "can_approve": payload.can_approve,
            "is_supervisor": payload.is_supervisor,
        },
    )
    db.commit()
    db.refresh(access)
    return access


@router.patch(
    "/companies/{company_id}/agents/{agent_instance_id}/access/{access_id}",
    response_model=AgentAccessRead,
)
def update_agent_access(
    company_id: str,
    agent_instance_id: str,
    access_id: str,
    payload: AgentAccessUpdate,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    agent = get_owned_agent_or_404(db, company_id, agent_instance_id)
    require_agent_manage(
        db, user, company_id=company_id, agent_instance_id=agent_instance_id
    )

    access = db.scalar(
        select(AgentAccess).where(
            AgentAccess.id == access_id,
            AgentAccess.company_id == company_id,
            AgentAccess.agent_instance_id == agent_instance_id,
        )
    )
    if not access:
        raise HTTPException(status_code=404, detail="Access grant not found")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(access, key, value)

    if data.get("is_supervisor") is True:
        agent.supervisor_user_id = access.user_id

    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        agent_instance_id=agent.id,
        action="agent.access.update",
        resource_type="agent_access",
        resource_id=access.id,
        status="success",
        details=data,
    )
    db.commit()
    db.refresh(access)
    return access


@router.delete(
    "/companies/{company_id}/agents/{agent_instance_id}/access/{access_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_agent_access(
    company_id: str,
    agent_instance_id: str,
    access_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    agent = get_owned_agent_or_404(db, company_id, agent_instance_id)
    require_agent_manage(
        db, user, company_id=company_id, agent_instance_id=agent_instance_id
    )

    access = db.scalar(
        select(AgentAccess).where(
            AgentAccess.id == access_id,
            AgentAccess.company_id == company_id,
            AgentAccess.agent_instance_id == agent_instance_id,
        )
    )
    if not access:
        raise HTTPException(status_code=404, detail="Access grant not found")

    if agent.supervisor_user_id == access.user_id:
        agent.supervisor_user_id = None

    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        agent_instance_id=agent.id,
        action="agent.access.revoke",
        resource_type="agent_access",
        resource_id=access.id,
        status="success",
        details={"target_user_id": access.user_id},
    )
    db.delete(access)
    db.commit()
    return None




@router.get(
    "/companies/{company_id}/skills",
    response_model=list[SkillRead],
)
def list_company_skills(
    company_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.read")
    return list_available_skills(db, company_id)


@router.post(
    "/companies/{company_id}/skills",
    response_model=SkillRead,
    status_code=status.HTTP_201_CREATED,
)
def create_company_skill(
    company_id: str,
    payload: SkillCreate,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.manage")

    existing = db.scalar(
        select(Skill).where(
            Skill.company_id == company_id,
            Skill.slug == payload.slug,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Skill slug already exists for company")

    skill = Skill(
        company_id=company_id,
        **payload.model_dump(),
        is_active=True,
    )
    db.add(skill)
    db.flush()
    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        action="skill.create",
        resource_type="skill",
        resource_id=skill.id,
        status="success",
        details={"slug": skill.slug},
    )
    db.commit()
    db.refresh(skill)
    return skill


@router.get(
    "/companies/{company_id}/agents/{agent_instance_id}/skills",
    response_model=list[AgentSkillRead],
)
def list_agent_skill_assignments(
    company_id: str,
    agent_instance_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    get_owned_agent_or_404(db, company_id, agent_instance_id)
    require_permission(user, "agent.read")
    return list_agent_skills(
        db, company_id=company_id, agent_instance_id=agent_instance_id
    )


@router.post(
    "/companies/{company_id}/agents/{agent_instance_id}/skills",
    response_model=AgentSkillRead,
    status_code=status.HTTP_201_CREATED,
)
def assign_agent_skill(
    company_id: str,
    agent_instance_id: str,
    payload: AgentSkillAssign,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    agent = get_owned_agent_or_404(db, company_id, agent_instance_id)
    require_agent_manage(
        db, user, company_id=company_id, agent_instance_id=agent.id
    )

    skill = get_skill_for_company(
        db, skill_id=payload.skill_id, company_id=company_id
    )
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found or not available")

    # Tool requirement enforcement: skill tools must be subset of agent allowed tools
    # if agent already has an allow-list; otherwise reject unknown tools later at runtime.
    agent_tools = set(agent.allowed_tools or [])
    skill_tools = set(skill.allowed_tools or [])
    if agent_tools and skill_tools and not skill_tools.issubset(agent_tools):
        extra = sorted(skill_tools - agent_tools)
        raise HTTPException(
            status_code=400,
            detail=(
                "Skill requires tools not allowed on this agent: "
                + ", ".join(extra)
            ),
        )

    row = assign_skill(
        db,
        company_id=company_id,
        agent_instance_id=agent.id,
        skill_id=skill.id,
    )
    # keep JSON skills list in sync
    current = list(agent.skills or [])
    if skill.slug not in current:
        current.append(skill.slug)
        agent.skills = current

    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        agent_instance_id=agent.id,
        action="agent.skill.assign",
        resource_type="agent_skill",
        resource_id=row.id,
        status="success",
        details={"skill_id": skill.id, "slug": skill.slug},
    )
    db.commit()
    db.refresh(row)
    return row


@router.delete(
    "/companies/{company_id}/agents/{agent_instance_id}/skills/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def unassign_agent_skill(
    company_id: str,
    agent_instance_id: str,
    assignment_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    agent = get_owned_agent_or_404(db, company_id, agent_instance_id)
    require_agent_manage(
        db, user, company_id=company_id, agent_instance_id=agent.id
    )

    row = db.scalar(
        select(AgentSkill).where(
            AgentSkill.id == assignment_id,
            AgentSkill.company_id == company_id,
            AgentSkill.agent_instance_id == agent_instance_id,
        )
    )
    if not row:
        raise HTTPException(status_code=404, detail="Skill assignment not found")

    skill = db.get(Skill, row.skill_id)
    if skill and agent.skills:
        agent.skills = [s for s in agent.skills if s != skill.slug]

    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        agent_instance_id=agent.id,
        action="agent.skill.unassign",
        resource_type="agent_skill",
        resource_id=row.id,
        status="success",
    )
    db.delete(row)
    db.commit()
    return None




@router.get(
    "/companies/{company_id}/policies",
    response_model=list[PolicyRead],
)
def list_company_policies(
    company_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.read")
    return list(
        db.scalars(
            select(Policy)
            .where(Policy.company_id == company_id)
            .order_by(Policy.name)
        ).all()
    )


@router.post(
    "/companies/{company_id}/policies",
    response_model=PolicyRead,
    status_code=status.HTTP_201_CREATED,
)
def create_company_policy(
    company_id: str,
    payload: PolicyCreate,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.manage")

    cfg = dict(payload.configuration or {})
    if not cfg.get("tool") and not cfg.get("action"):
        raise HTTPException(
            status_code=400,
            detail="configuration.tool (or action) is required",
        )
    if not cfg.get("effect"):
        raise HTTPException(
            status_code=400,
            detail="configuration.effect is required (allow|require_approval|deny)",
        )

    policy = Policy(
        company_id=company_id,
        name=payload.name,
        description=payload.description or "",
        configuration=cfg,
        is_active=payload.is_active,
    )
    db.add(policy)
    db.flush()
    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        action="policy.create",
        resource_type="policy",
        resource_id=policy.id,
        status="success",
        details={"name": policy.name, "tool": cfg.get("tool") or cfg.get("action")},
    )
    db.commit()
    db.refresh(policy)
    return policy


@router.patch(
    "/companies/{company_id}/policies/{policy_id}",
    response_model=PolicyRead,
)
def update_company_policy(
    company_id: str,
    policy_id: str,
    payload: PolicyUpdate,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.manage")

    policy = db.scalar(
        select(Policy).where(
            Policy.id == policy_id,
            Policy.company_id == company_id,
        )
    )
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(policy, key, value)

    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        action="policy.update",
        resource_type="policy",
        resource_id=policy.id,
        status="success",
        details=data,
    )
    db.commit()
    db.refresh(policy)
    return policy


@router.delete(
    "/companies/{company_id}/policies/{policy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_company_policy(
    company_id: str,
    policy_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.manage")

    policy = db.scalar(
        select(Policy).where(
            Policy.id == policy_id,
            Policy.company_id == company_id,
        )
    )
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        action="policy.delete",
        resource_type="policy",
        resource_id=policy.id,
        status="success",
    )
    db.delete(policy)
    db.commit()
    return None




@router.post(
    "/companies/{company_id}/knowledge/search",
    response_model=list[KnowledgeSearchHit],
)
def search_company_knowledge(
    company_id: str,
    payload: KnowledgeSearchRequest,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
    agent_instance_id: str | None = None,
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "knowledge.read")

    hits = search_knowledge_chunks(
        db,
        company_id=company_id,
        agent_instance_id=agent_instance_id,
        query=payload.query,
        limit=payload.limit,
    )
    if len(hits) < payload.limit:
        items = search_knowledge_items(
            db,
            company_id=company_id,
            agent_instance_id=agent_instance_id,
            query=payload.query,
            limit=payload.limit - len(hits),
        )
        hits.extend(items)
    return hits


@router.get(
    "/companies/{company_id}/agents/{agent_instance_id}/memories",
    response_model=list[AgentMemoryRead],
)
def list_agent_memories(
    company_id: str,
    agent_instance_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    get_owned_agent_or_404(db, company_id, agent_instance_id)
    require_permission(user, "agent.read")
    return active_agent_memories(
        db, company_id=company_id, agent_instance_id=agent_instance_id, limit=50
    )


@router.post(
    "/companies/{company_id}/agents/{agent_instance_id}/memories",
    response_model=AgentMemoryRead,
    status_code=status.HTTP_201_CREATED,
)
def create_agent_memory(
    company_id: str,
    agent_instance_id: str,
    payload: AgentMemoryCreate,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    agent = get_owned_agent_or_404(db, company_id, agent_instance_id)
    require_agent_manage(
        db, user, company_id=company_id, agent_instance_id=agent.id
    )

    memory = AgentMemory(
        company_id=company_id,
        agent_instance_id=agent.id,
        title=payload.title,
        content=payload.content,
        category=payload.category,
        source_task_id=payload.source_task_id,
        expires_at=payload.expires_at,
        is_active=True,
    )
    db.add(memory)
    db.flush()
    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        agent_instance_id=agent.id,
        task_id=payload.source_task_id,
        action="memory.create",
        resource_type="agent_memory",
        resource_id=memory.id,
        status="success",
    )
    db.commit()
    db.refresh(memory)
    return memory


@router.patch(
    "/companies/{company_id}/agents/{agent_instance_id}/memories/{memory_id}",
    response_model=AgentMemoryRead,
)
def update_agent_memory(
    company_id: str,
    agent_instance_id: str,
    memory_id: str,
    payload: AgentMemoryUpdate,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    agent = get_owned_agent_or_404(db, company_id, agent_instance_id)
    require_agent_manage(
        db, user, company_id=company_id, agent_instance_id=agent.id
    )

    memory = db.scalar(
        select(AgentMemory).where(
            AgentMemory.id == memory_id,
            AgentMemory.company_id == company_id,
            AgentMemory.agent_instance_id == agent_instance_id,
        )
    )
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(memory, key, value)

    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        agent_instance_id=agent.id,
        action="memory.update",
        resource_type="agent_memory",
        resource_id=memory.id,
        status="success",
        details=data,
    )
    db.commit()
    db.refresh(memory)
    return memory


@router.delete(
    "/companies/{company_id}/agents/{agent_instance_id}/memories/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_agent_memory(
    company_id: str,
    agent_instance_id: str,
    memory_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    agent = get_owned_agent_or_404(db, company_id, agent_instance_id)
    require_agent_manage(
        db, user, company_id=company_id, agent_instance_id=agent.id
    )

    memory = db.scalar(
        select(AgentMemory).where(
            AgentMemory.id == memory_id,
            AgentMemory.company_id == company_id,
            AgentMemory.agent_instance_id == agent_instance_id,
        )
    )
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    # soft delete via lifecycle
    memory.is_active = False
    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        agent_instance_id=agent.id,
        action="memory.deactivate",
        resource_type="agent_memory",
        resource_id=memory.id,
        status="success",
    )
    db.commit()
    return None




@router.get(
    "/companies/{company_id}/experiences",
    response_model=list[ExperienceRead],
)
def list_company_experiences(
    company_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
    status_filter: str | None = None,
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.read")
    q = select(Experience).where(
        Experience.company_id == company_id,
        Experience.is_active.is_(True),
    )
    if status_filter:
        q = q.where(Experience.validation_status == status_filter)
    return list(db.scalars(q.order_by(Experience.created_at.desc())).all())


@router.post(
    "/companies/{company_id}/experiences",
    response_model=ExperienceRead,
    status_code=status.HTTP_201_CREATED,
)
def create_experience_candidate(
    company_id: str,
    payload: ExperienceCreate,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "task.create")

    agent_id = payload.agent_instance_id
    if payload.source_task_id:
        task = db.scalar(
            select(Task).where(
                Task.id == payload.source_task_id,
                Task.company_id == company_id,
            )
        )
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        agent_id = task.agent_instance_id
        exp = Experience(
            company_id=company_id,
            agent_instance_id=agent_id,
            source_task_id=task.id,
            situation=payload.situation or task.title,
            context=payload.context,
            problem=payload.problem or task.instruction,
            decision=payload.decision,
            action=payload.action,
            result=payload.result or (task.result or ""),
            human_correction=payload.human_correction,
            lesson=payload.lesson,
            confidence=payload.confidence,
            validation_status="candidate",
        )
    else:
        if agent_id:
            get_owned_agent_or_404(db, company_id, agent_id)
        exp = Experience(
            company_id=company_id,
            agent_instance_id=agent_id,
            source_task_id=None,
            situation=payload.situation,
            context=payload.context,
            problem=payload.problem,
            decision=payload.decision,
            action=payload.action,
            result=payload.result,
            human_correction=payload.human_correction,
            lesson=payload.lesson,
            confidence=payload.confidence,
            validation_status="candidate",
        )

    db.add(exp)
    db.flush()
    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        agent_instance_id=exp.agent_instance_id,
        task_id=exp.source_task_id,
        action="experience.candidate",
        resource_type="experience",
        resource_id=exp.id,
        status="success",
    )
    db.commit()
    db.refresh(exp)
    return exp


@router.post(
    "/companies/{company_id}/tasks/{task_id}/experiences",
    response_model=ExperienceRead,
    status_code=status.HTTP_201_CREATED,
)
def create_experience_from_task(
    company_id: str,
    task_id: str,
    payload: ExperienceFromTaskRequest,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "task.create")

    task = db.scalar(
        select(Task).where(Task.id == task_id, Task.company_id == company_id)
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    exp = create_candidate_from_task(
        db,
        task=task,
        decision=payload.decision,
        action=payload.action,
        human_correction=payload.human_correction,
        lesson=payload.lesson,
        confidence=payload.confidence,
    )
    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        agent_instance_id=task.agent_instance_id,
        task_id=task.id,
        action="experience.candidate",
        resource_type="experience",
        resource_id=exp.id,
        status="success",
    )
    db.commit()
    db.refresh(exp)
    return exp


@router.post(
    "/companies/{company_id}/experiences/{experience_id}/validate",
    response_model=ExperienceRead,
)
def validate_company_experience(
    company_id: str,
    experience_id: str,
    payload: ExperienceValidateRequest,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    # validation is a management/governance action
    require_permission(user, "agent.manage")

    exp = db.scalar(
        select(Experience).where(
            Experience.id == experience_id,
            Experience.company_id == company_id,
        )
    )
    if not exp:
        raise HTTPException(status_code=404, detail="Experience not found")

    if exp.validation_status not in ("candidate", "validated"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot validate experience in status '{exp.validation_status}'",
        )

    validate_experience(
        db,
        experience=exp,
        user_id=user.id,
        approve=payload.approve,
        lesson=payload.lesson,
        confidence=payload.confidence,
        human_correction=payload.human_correction,
    )
    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        agent_instance_id=exp.agent_instance_id,
        task_id=exp.source_task_id,
        action="experience.validate" if payload.approve else "experience.reject",
        resource_type="experience",
        resource_id=exp.id,
        status="success",
        details={"approve": payload.approve},
    )
    db.commit()
    db.refresh(exp)
    return exp




@router.get(
    "/companies/{company_id}/experiences/{experience_id}",
    response_model=ExperienceRead,
)
def get_company_experience(
    company_id: str,
    experience_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.read")
    exp = get_experience_for_company(
        db, company_id=company_id, experience_id=experience_id
    )
    if not exp:
        raise HTTPException(status_code=404, detail="Experience not found")
    return exp


@router.post(
    "/companies/{company_id}/experiences/{experience_id}/feedback",
    response_model=ExperienceRead,
)
def feedback_company_experience(
    company_id: str,
    experience_id: str,
    payload: ExperienceFeedbackRequest,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    """Job 10 — human feedback on a validated experience (confidence + correction)."""
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.manage")
    exp = get_experience_for_company(
        db, company_id=company_id, experience_id=experience_id
    )
    if not exp:
        raise HTTPException(status_code=404, detail="Experience not found")
    try:
        submit_feedback(
            db,
            experience=exp,
            user_id=user.id,
            helpful=payload.helpful,
            human_correction=payload.human_correction,
            lesson=payload.lesson,
            confidence_delta=payload.confidence_delta,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        agent_instance_id=exp.agent_instance_id,
        task_id=exp.source_task_id,
        action="experience.feedback",
        resource_type="experience",
        resource_id=exp.id,
        status="success",
        details={
            "helpful": payload.helpful,
            "confidence": exp.confidence,
            "success_count": exp.success_count,
        },
    )
    db.commit()
    db.refresh(exp)
    return exp


@router.post(
    "/companies/{company_id}/experiences/{experience_id}/reuse",
    response_model=ExperienceRead,
)
def reuse_company_experience(
    company_id: str,
    experience_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    """Record that a validated experience was reused successfully (confidence nudge)."""
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "task.create")
    exp = get_experience_for_company(
        db, company_id=company_id, experience_id=experience_id
    )
    if not exp:
        raise HTTPException(status_code=404, detail="Experience not found")
    if exp.validation_status != "validated":
        raise HTTPException(
            status_code=409,
            detail="Only validated experiences can be marked reused",
        )
    record_successful_reuse(db, exp.id)
    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        agent_instance_id=exp.agent_instance_id,
        action="experience.reuse",
        resource_type="experience",
        resource_id=exp.id,
        status="success",
        details={"success_count": exp.success_count, "confidence": exp.confidence},
    )
    db.commit()
    db.refresh(exp)
    return exp


@router.post(
    "/companies/{company_id}/experiences/{experience_id}/archive",
    response_model=ExperienceRead,
)
def archive_company_experience(
    company_id: str,
    experience_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.manage")
    exp = get_experience_for_company(
        db, company_id=company_id, experience_id=experience_id
    )
    if not exp:
        raise HTTPException(status_code=404, detail="Experience not found")
    archive_experience(db, experience=exp)
    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        agent_instance_id=exp.agent_instance_id,
        action="experience.archive",
        resource_type="experience",
        resource_id=exp.id,
        status="success",
    )
    db.commit()
    db.refresh(exp)
    return exp


@router.post(
    "/companies/{company_id}/experiences/search",
    response_model=list[ExperienceSearchHit],
)
def search_company_experiences(
    company_id: str,
    payload: ExperienceSearchRequest,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.read")
    return search_validated_experiences(
        db,
        company_id=company_id,
        agent_instance_id=payload.agent_instance_id,
        query=payload.query,
        limit=payload.limit,
        min_confidence=payload.min_confidence,
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
    replace_chunks_for_item(db, item)

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
    replace_chunks_for_item(db, item)

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





@router.get(
    "/companies/{company_id}/departments",
    response_model=list[DepartmentRead],
)
def list_departments(
    company_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.read")
    return list(
        db.scalars(
            select(Department)
            .where(Department.company_id == company_id)
            .order_by(Department.name)
        ).all()
    )


@router.post(
    "/companies/{company_id}/departments",
    response_model=DepartmentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_department(
    company_id: str,
    payload: DepartmentCreate,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "team.manage")
    existing = db.scalar(
        select(Department).where(
            Department.company_id == company_id,
            Department.name == payload.name,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Department name already exists")
    dept = Department(
        company_id=company_id,
        name=payload.name,
        description=payload.description or "",
        is_active=payload.is_active,
    )
    db.add(dept)
    db.flush()
    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        action="department.create",
        resource_type="department",
        resource_id=dept.id,
        status="success",
    )
    db.commit()
    db.refresh(dept)
    return dept


@router.patch(
    "/companies/{company_id}/departments/{department_id}",
    response_model=DepartmentRead,
)
def update_department(
    company_id: str,
    department_id: str,
    payload: DepartmentUpdate,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "team.manage")
    dept = db.scalar(
        select(Department).where(
            Department.id == department_id,
            Department.company_id == company_id,
        )
    )
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(dept, k, v)
    db.commit()
    db.refresh(dept)
    return dept


@router.get(
    "/companies/{company_id}/teams",
    response_model=list[AgentTeamRead],
)
def list_agent_teams(
    company_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
    department_id: str | None = None,
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.read")
    q = select(AgentTeam).where(AgentTeam.company_id == company_id)
    if department_id:
        q = q.where(AgentTeam.department_id == department_id)
    teams = list(db.scalars(q.order_by(AgentTeam.name)).all())
    result = []
    for team in teams:
        member_ids = [
            m.agent_instance_id
            for m in db.scalars(
                select(AgentTeamMember).where(AgentTeamMember.team_id == team.id)
            ).all()
        ]
        result.append(
            AgentTeamRead(
                id=team.id,
                company_id=team.company_id,
                department_id=team.department_id,
                name=team.name,
                description=team.description,
                is_active=team.is_active,
                created_at=team.created_at,
                updated_at=team.updated_at,
                member_agent_ids=member_ids,
            )
        )
    return result


@router.post(
    "/companies/{company_id}/teams",
    response_model=AgentTeamRead,
    status_code=status.HTTP_201_CREATED,
)
def create_agent_team(
    company_id: str,
    payload: AgentTeamCreate,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.manage")
    if payload.department_id:
        dept = db.scalar(
            select(Department).where(
                Department.id == payload.department_id,
                Department.company_id == company_id,
            )
        )
        if not dept:
            raise HTTPException(status_code=400, detail="Department not found")
    existing = db.scalar(
        select(AgentTeam).where(
            AgentTeam.company_id == company_id,
            AgentTeam.name == payload.name,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Team name already exists")
    team = AgentTeam(
        company_id=company_id,
        department_id=payload.department_id,
        name=payload.name,
        description=payload.description or "",
        is_active=payload.is_active,
    )
    db.add(team)
    db.flush()
    member_ids = []
    for aid in payload.agent_instance_ids or []:
        agent = get_owned_agent_or_404(db, company_id, aid)
        mem = AgentTeamMember(
            company_id=company_id,
            team_id=team.id,
            agent_instance_id=agent.id,
        )
        db.add(mem)
        member_ids.append(agent.id)
    db.flush()
    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        action="agent_team.create",
        resource_type="agent_team",
        resource_id=team.id,
        status="success",
        details={"members": member_ids},
    )
    db.commit()
    db.refresh(team)
    return AgentTeamRead(
        id=team.id,
        company_id=team.company_id,
        department_id=team.department_id,
        name=team.name,
        description=team.description,
        is_active=team.is_active,
        created_at=team.created_at,
        updated_at=team.updated_at,
        member_agent_ids=member_ids,
    )


@router.post(
    "/companies/{company_id}/teams/{team_id}/members",
    response_model=AgentTeamRead,
)
def add_team_members(
    company_id: str,
    team_id: str,
    payload: AgentTeamAddMembers,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.manage")
    team = db.scalar(
        select(AgentTeam).where(
            AgentTeam.id == team_id,
            AgentTeam.company_id == company_id,
        )
    )
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    for aid in payload.agent_instance_ids:
        agent = get_owned_agent_or_404(db, company_id, aid)
        exists = db.scalar(
            select(AgentTeamMember).where(
                AgentTeamMember.team_id == team.id,
                AgentTeamMember.agent_instance_id == agent.id,
            )
        )
        if exists:
            continue
        db.add(
            AgentTeamMember(
                company_id=company_id,
                team_id=team.id,
                agent_instance_id=agent.id,
            )
        )
    db.commit()
    member_ids = [
        m.agent_instance_id
        for m in db.scalars(
            select(AgentTeamMember).where(AgentTeamMember.team_id == team.id)
        ).all()
    ]
    return AgentTeamRead(
        id=team.id,
        company_id=team.company_id,
        department_id=team.department_id,
        name=team.name,
        description=team.description,
        is_active=team.is_active,
        created_at=team.created_at,
        updated_at=team.updated_at,
        member_agent_ids=member_ids,
    )




@router.get(
    "/companies/{company_id}/notifications",
)
def list_user_notifications(
    company_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
    unread_only: bool = False,
    limit: int = 50,
):
    """Job 20 — list notifications for the current user."""
    from app.services.notifications import list_notifications

    user = require_company_user(db, company_id, x_user_id)
    notes = list_notifications(
        db,
        company_id=company_id,
        user_id=user.id,
        unread_only=unread_only,
        limit=limit,
    )
    return [
        {
            "id": n.id,
            "company_id": n.company_id,
            "user_id": n.user_id,
            "type": n.type,
            "title": n.title,
            "body": n.body,
            "payload": n.payload,
            "read_at": n.read_at.isoformat() if n.read_at else None,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in notes
    ]


@router.get(
    "/companies/{company_id}/notifications/unread-count",
)
def notifications_unread_count(
    company_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    from app.services.notifications import unread_count

    user = require_company_user(db, company_id, x_user_id)
    return {"count": unread_count(db, company_id=company_id, user_id=user.id)}


@router.post(
    "/companies/{company_id}/notifications/{notification_id}/read",
)
def mark_notification_read(
    company_id: str,
    notification_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    from app.services.notifications import mark_read

    user = require_company_user(db, company_id, x_user_id)
    note = mark_read(
        db,
        company_id=company_id,
        user_id=user.id,
        notification_id=notification_id,
    )
    if not note:
        raise HTTPException(status_code=404, detail="Notification not found")
    db.commit()
    return {
        "id": note.id,
        "read_at": note.read_at.isoformat() if note.read_at else None,
    }


@router.post(
    "/companies/{company_id}/notifications/read-all",
)
def mark_all_notifications_read(
    company_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    from app.services.notifications import mark_all_read

    user = require_company_user(db, company_id, x_user_id)
    n = mark_all_read(db, company_id=company_id, user_id=user.id)
    db.commit()
    return {"marked": n}


@router.get(
    "/companies/{company_id}/conversations",
    response_model=list[ConversationRead],
)
def list_conversations_api(
    company_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
    agent_instance_id: str | None = None,
):
    from app.services.conversation import list_conversations

    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.read")
    return list_conversations(
        db,
        company_id=company_id,
        user_id=None,
        agent_instance_id=agent_instance_id,
    )


@router.post(
    "/companies/{company_id}/conversations",
    response_model=ConversationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation_api(
    company_id: str,
    payload: ConversationCreate,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    from app.services.conversation import create_conversation

    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "task.create")
    agent = get_owned_agent_or_404(db, company_id, payload.agent_instance_id)
    require_agent_use(
        db, user, company_id=company_id, agent_instance_id=agent.id
    )
    try:
        conv = create_conversation(
            db,
            company_id=company_id,
            agent_instance_id=agent.id,
            user_id=user.id,
            title=payload.title,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(conv)
    return conv


@router.get(
    "/companies/{company_id}/conversations/{conversation_id}/messages",
    response_model=list[MessageRead],
)
def list_messages_api(
    company_id: str,
    conversation_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    from app.services.conversation import get_conversation, list_messages

    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.read")
    conv = get_conversation(
        db, company_id=company_id, conversation_id=conversation_id
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return list_messages(
        db, company_id=company_id, conversation_id=conversation_id
    )


@router.post(
    "/companies/{company_id}/conversations/{conversation_id}/messages",
    response_model=ChatPostResponse,
)
def post_message_api(
    company_id: str,
    conversation_id: str,
    payload: MessageCreate,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    """
    Post human message + advisory agent reply.
    Tools are NEVER run here. Optional create_task links a Task for later execution.
    """
    from app.services.conversation import get_conversation, post_human_message

    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "task.create")
    conv = get_conversation(
        db, company_id=company_id, conversation_id=conversation_id
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    require_agent_use(
        db, user, company_id=company_id, agent_instance_id=conv.agent_instance_id
    )
    try:
        result = post_human_message(
            db,
            company_id=company_id,
            conversation_id=conversation_id,
            user_id=user.id,
            content=payload.content,
            create_task=payload.create_task,
            task_mode=payload.task_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    human = result["human"]
    agent = result["agent"]
    task = result["task"]
    return ChatPostResponse(
        human=MessageRead.model_validate(human),
        agent=MessageRead.model_validate(agent),
        task_id=task.id if task else None,
    )


@router.get("/plans")
def list_plans(db: Session = Depends(get_db)):
    from app.services.quotas import seed_default_plans
    from app.models.entities import Plan
    seed_default_plans(db)
    db.commit()
    plans = list(db.scalars(select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.code)).all())
    return [
        {
            "id": p.id,
            "code": p.code,
            "name": p.name,
            "description": p.description,
            "max_agents": p.max_agents,
            "max_tasks_day": p.max_tasks_day,
            "max_automations": p.max_automations,
            "max_llm_calls_day": p.max_llm_calls_day,
        }
        for p in plans
    ]


@router.get("/companies/{company_id}/usage")
def get_company_usage(
    company_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    from app.services.quotas import usage_summary
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.read")
    summary = usage_summary(db, company_id)
    db.commit()
    return summary


@router.put("/companies/{company_id}/plan")
def set_company_plan_api(
    company_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    """Assign plan by code (owner/admin). No payment gateway yet."""
    from app.services.quotas import set_company_plan, usage_summary
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "team.manage")
    code = str(payload.get("plan_code") or payload.get("code") or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="plan_code required")
    try:
        set_company_plan(db, company_id, code)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return usage_summary(db, company_id)

@router.get("/tools")
def list_platform_tools():
    """Job 19 — global tool catalog (metadata: side_effect, risk)."""
    from app.tools.domain import build_default_tools
    from app.core.database import SessionLocal

    with SessionLocal() as db:
        tools = build_default_tools(db)
        return [t.to_catalog_dict() for t in tools]


@router.post(
    "/companies/{company_id}/policies/simulate",
)
def simulate_policy(
    company_id: str,
    payload: PolicySimulateRequest,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    """Job 17 — dry-run policy decision with explanation trail."""
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.read")
    agent = get_owned_agent_or_404(db, company_id, payload.agent_instance_id)
    engine = get_policy_engine(db)
    result = engine.simulate(
        company_id=company_id,
        agent_instance_id=agent.id,
        tool_name=payload.tool_name,
        arguments=payload.arguments,
        context=payload.context,
    )
    return result

@router.post(
    "/companies/{company_id}/scope-check",
)
def scope_check_endpoint(
    company_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    """Job 16 — check whether instruction fits agent scope; suggest specialists."""
    from app.schemas.domain import ScopeCheckRequest

    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "task.create")
    body = ScopeCheckRequest.model_validate(payload)
    agent = get_owned_agent_or_404(db, company_id, body.agent_instance_id)
    result = check_scope(
        db,
        company_id=company_id,
        agent=agent,
        instruction=body.instruction,
        auto_delegate=body.auto_delegate,
        user_id=user.id,
    )
    db.commit()
    return result.to_dict()


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

    require_agent_use(
        db,
        user,
        company_id=company_id,
        agent_instance_id=agent.id,
    )

    from app.services.quotas import enforce_task_quota, record_task_created
    enforce_task_quota(db, company_id)

    data = payload.model_dump()
    check_scope_flag = bool(data.pop("check_scope", False))
    auto_delegate_flag = bool(data.pop("auto_delegate", False))
    block_oos = bool(data.pop("block_out_of_scope", True))

    task = Task(
        company_id=company_id,
        **data,
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

    if check_scope_flag:
        enforce_scope_on_task(
            db,
            company_id=company_id,
            agent=agent,
            task=task,
            auto_delegate=auto_delegate_flag,
            user_id=user.id,
            block_out_of_scope=block_oos,
        )

    record_task_created(db, company_id)

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






@router.get(
    "/companies/{company_id}/directory",
    response_model=list[AgentDirectoryEntry],
)
def get_agent_directory(
    company_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    """List active AI Employees with capability registry cards."""
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.read")
    cards = list_directory(db, company_id=company_id, active_only=True)
    return [c.to_dict() for c in cards]


@router.get(
    "/companies/{company_id}/directory/search",
    response_model=list[AgentDirectoryEntry],
)
def search_agent_directory(
    company_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
    capability: str | None = None,
    skill: str | None = None,
    tool: str | None = None,
    role: str | None = None,
    exclude_agent_id: str | None = None,
):
    """Discover agents by capability / skill / tool / role."""
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.read")
    cards = discover_agents(
        db,
        company_id=company_id,
        capability=capability,
        skill=skill,
        tool=tool,
        role=role,
        exclude_agent_id=exclude_agent_id,
    )
    return [c.to_dict() for c in cards]


@router.post(
    "/companies/{company_id}/directory/validate-target",
    response_model=TargetValidationResult,
)
def validate_directory_target(
    company_id: str,
    payload: TargetValidationRequest,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    """Validate a target agent for structured delegation."""
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.read")
    result = validate_delegation_target(
        db,
        company_id=company_id,
        target_agent_instance_id=payload.target_agent_instance_id,
        required_capability=payload.required_capability,
        source_agent_instance_id=payload.source_agent_instance_id,
    )
    return result.to_dict()


@router.post(
    "/companies/{company_id}/delegation-requests",
    response_model=DelegationRequestRead,
    status_code=status.HTTP_201_CREATED,
)
def create_delegation_request(
    company_id: str,
    payload: DelegationRequestCreate,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    """
    Create a structured delegation request after target validation.

    Execution of the delegated work is Job 09; this endpoint only
    records a validated request.
    """
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "task.create")

    # Source must exist and be usable
    source = get_owned_agent_or_404(
        db, company_id, payload.source_agent_instance_id
    )
    require_agent_use(
        db, user, company_id=company_id, agent_instance_id=source.id
    )

    validation = validate_delegation_target(
        db,
        company_id=company_id,
        target_agent_instance_id=payload.target_agent_instance_id,
        required_capability=payload.capability,
        source_agent_instance_id=payload.source_agent_instance_id,
    )
    if not validation.valid:
        raise HTTPException(status_code=400, detail=validation.reason)

    req = DelegationRequest(
        company_id=company_id,
        source_agent_instance_id=payload.source_agent_instance_id,
        target_agent_instance_id=payload.target_agent_instance_id,
        requested_by_user_id=user.id,
        capability=payload.capability,
        title=payload.title,
        instruction=payload.instruction,
        status="pending",
        validation_notes=validation.reason,
        timeout_seconds=payload.timeout_seconds,
    )
    db.add(req)
    db.flush()
    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        agent_instance_id=payload.source_agent_instance_id,
        action="delegation.request",
        resource_type="delegation_request",
        resource_id=req.id,
        status="success",
        details={
            "target_agent_instance_id": payload.target_agent_instance_id,
            "capability": payload.capability,
        },
    )
    # Job 20 — notify target agent supervisor
    from app.models.entities import NotificationType
    from app.services.notifications import emit_notification
    target = get_owned_agent_or_404(
        db, company_id, payload.target_agent_instance_id
    )
    if target.supervisor_user_id:
        emit_notification(
            db,
            company_id=company_id,
            user_id=target.supervisor_user_id,
            type=NotificationType.DELEGATION_RECEIVED.value,
            title=f"Delegation received: {payload.title}",
            body=payload.instruction[:500],
            payload={
                "delegation_request_id": req.id,
                "source_agent_instance_id": payload.source_agent_instance_id,
                "target_agent_instance_id": payload.target_agent_instance_id,
            },
        )
    db.commit()
    db.refresh(req)
    return req


@router.get(
    "/companies/{company_id}/delegation-requests",
    response_model=list[DelegationRequestRead],
)
def list_delegation_requests(
    company_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.read")
    return list(
        db.scalars(
            select(DelegationRequest)
            .where(DelegationRequest.company_id == company_id)
            .order_by(DelegationRequest.created_at.desc())
        ).all()
    )




@router.get(
    "/companies/{company_id}/delegation-requests/{request_id}",
    response_model=DelegationRequestRead,
)
def get_delegation_request(
    company_id: str,
    request_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.read")
    req = db.scalar(
        select(DelegationRequest).where(
            DelegationRequest.id == request_id,
            DelegationRequest.company_id == company_id,
        )
    )
    if not req:
        raise HTTPException(status_code=404, detail="Delegation request not found")
    mark_timeout_if_needed(db, req)
    db.commit()
    db.refresh(req)
    return req


@router.post(
    "/companies/{company_id}/delegation-requests/{request_id}/accept",
    response_model=DelegationRequestRead,
)
def accept_delegation_request(
    company_id: str,
    request_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "task.create")
    req = db.scalar(
        select(DelegationRequest).where(
            DelegationRequest.id == request_id,
            DelegationRequest.company_id == company_id,
        )
    )
    if not req:
        raise HTTPException(status_code=404, detail="Delegation request not found")
    try:
        accept_delegation(db, req=req, user_id=user.id)
        db.commit()
        db.refresh(req)
        return req
    except ValueError as exc:
        db.commit()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/companies/{company_id}/delegation-requests/{request_id}/reject",
    response_model=DelegationRequestRead,
)
def reject_delegation_request(
    company_id: str,
    request_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
    reason: str = "",
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "task.create")
    req = db.scalar(
        select(DelegationRequest).where(
            DelegationRequest.id == request_id,
            DelegationRequest.company_id == company_id,
        )
    )
    if not req:
        raise HTTPException(status_code=404, detail="Delegation request not found")
    try:
        reject_delegation(db, req=req, user_id=user.id, reason=reason)
        db.commit()
        db.refresh(req)
        return req
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/companies/{company_id}/delegation-requests/{request_id}/cancel",
    response_model=DelegationRequestRead,
)
def cancel_delegation_request(
    company_id: str,
    request_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "task.create")
    req = db.scalar(
        select(DelegationRequest).where(
            DelegationRequest.id == request_id,
            DelegationRequest.company_id == company_id,
        )
    )
    if not req:
        raise HTTPException(status_code=404, detail="Delegation request not found")
    try:
        cancel_delegation(db, req=req, user_id=user.id)
        db.commit()
        db.refresh(req)
        return req
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/companies/{company_id}/delegation-requests/{request_id}/execute",
    response_model=DelegationRequestRead,
)
def execute_delegation_request(
    company_id: str,
    request_id: str,
    payload: DelegationExecuteRequest | None = None,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    """
    Run inter-agent delegation: create child task on target, optionally
    complete via consultation, propagate result to source.
    """
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "task.create")
    req = db.scalar(
        select(DelegationRequest).where(
            DelegationRequest.id == request_id,
            DelegationRequest.company_id == company_id,
        )
    )
    if not req:
        raise HTTPException(status_code=404, detail="Delegation request not found")

    mode = (payload.mode if payload else "consult") or "consult"
    try:
        return execute_delegation(
            db, req=req, user_id=user.id, mode=mode
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/companies/{company_id}/delegation-requests/{request_id}/propagate",
    response_model=DelegationRequestRead,
)
def propagate_delegation_result(
    company_id: str,
    request_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    """Propagate completed child task result back to the delegation request."""
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "task.create")
    req = db.scalar(
        select(DelegationRequest).where(
            DelegationRequest.id == request_id,
            DelegationRequest.company_id == company_id,
        )
    )
    if not req:
        raise HTTPException(status_code=404, detail="Delegation request not found")
    try:
        return propagate_child_task_result(db, req=req)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc




@router.get(
    "/companies/{company_id}/automations",
    response_model=list[AutomationRuleRead],
)
def list_automation_rules(
    company_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.read")
    return list(
        db.scalars(
            select(AutomationRule)
            .where(AutomationRule.company_id == company_id)
            .order_by(AutomationRule.created_at.desc())
        ).all()
    )


@router.post(
    "/companies/{company_id}/automations",
    response_model=AutomationRuleRead,
    status_code=status.HTTP_201_CREATED,
)
def create_automation_rule(
    company_id: str,
    payload: AutomationRuleCreate,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.manage")
    agent = get_owned_agent_or_404(db, company_id, payload.agent_instance_id)

    from app.services.quotas import enforce_automation_quota
    enforce_automation_quota(db, company_id)

    if payload.trigger_type == "schedule":
        if not payload.interval_seconds:
            raise HTTPException(
                status_code=400,
                detail="interval_seconds required for schedule triggers",
            )
    if payload.trigger_type == "event":
        if not payload.event_type:
            raise HTTPException(
                status_code=400,
                detail="event_type required for event triggers",
            )

    from datetime import datetime, timezone

    next_run = payload.next_run_at
    if payload.trigger_type == "schedule" and next_run is None:
        next_run = datetime.now(timezone.utc)

    rule = AutomationRule(
        company_id=company_id,
        agent_instance_id=agent.id,
        name=payload.name,
        description=payload.description or "",
        trigger_type=payload.trigger_type,
        interval_seconds=payload.interval_seconds,
        next_run_at=next_run,
        event_type=payload.event_type,
        task_title_template=payload.task_title_template,
        task_instruction_template=payload.task_instruction_template,
        task_mode=payload.task_mode,
        max_retries=payload.max_retries,
        is_active=payload.is_active,
    )
    db.add(rule)
    db.flush()
    record_audit(
        db,
        company_id=company_id,
        user_id=user.id,
        agent_instance_id=agent.id,
        action="automation.rule.create",
        resource_type="automation_rule",
        resource_id=rule.id,
        status="success",
        details={"trigger_type": rule.trigger_type},
    )
    db.commit()
    db.refresh(rule)
    return rule


@router.post(
    "/companies/{company_id}/automations/tick",
    response_model=list[AutomationRunRead],
)
def tick_company_automations(
    company_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    """Process due scheduled automations (call from cron or manually)."""
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.manage")
    return tick_schedules(db, company_id=company_id, user_id=user.id)


@router.post(
    "/companies/{company_id}/automations/events",
    response_model=list[AutomationRunRead],
)
def fire_company_automation_event(
    company_id: str,
    payload: AutomationEventRequest,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "task.create")
    return fire_event(
        db,
        company_id=company_id,
        event_type=payload.event_type,
        payload=payload.payload,
        idempotency_key=payload.idempotency_key,
        user_id=user.id,
    )


@router.get(
    "/companies/{company_id}/automations/runs",
    response_model=list[AutomationRunRead],
)
def list_automation_runs(
    company_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
    rule_id: str | None = None,
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.read")
    q = select(AutomationRun).where(AutomationRun.company_id == company_id)
    if rule_id:
        q = q.where(AutomationRun.rule_id == rule_id)
    return list(db.scalars(q.order_by(AutomationRun.created_at.desc())).all())


@router.post(
    "/companies/{company_id}/automations/runs/{run_id}/retry",
    response_model=AutomationRunRead,
)
def retry_automation_run(
    company_id: str,
    run_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.manage")
    run = db.scalar(
        select(AutomationRun).where(
            AutomationRun.id == run_id,
            AutomationRun.company_id == company_id,
        )
    )
    if not run:
        raise HTTPException(status_code=404, detail="Automation run not found")
    try:
        return retry_run(db, run=run, user_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc




@router.get(
    "/companies/{company_id}/governance/overview",
)
def governance_overview(
    company_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    """Job 14 — company-wide performance & governance snapshot."""
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.read")
    return company_overview(db, company_id=company_id)


@router.get(
    "/companies/{company_id}/governance/agents",
)
def governance_agents(
    company_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.read")
    return agent_performance(db, company_id=company_id)


@router.get(
    "/companies/{company_id}/governance/approvals",
)
def governance_approvals(
    company_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.read")
    return approval_metrics(db, company_id=company_id)


@router.get(
    "/companies/{company_id}/governance/experiences",
)
def governance_experiences(
    company_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.read")
    return experience_quality(db, company_id=company_id)


@router.get(
    "/companies/{company_id}/governance/audit",
)
def governance_audit(
    company_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
    limit: int = 100,
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "agent.read")
    return audit_analytics(db, company_id=company_id, limit=min(limit, 500))


@router.post(
    "/companies/{company_id}/tasks/{task_id}/consult",
    response_model=TaskRead,
)
def consult_task(
    company_id: str,
    task_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    """
    Run consultation mode: recommendation only, no side-effect tools.
    Task must have mode=consult.
    """
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "task.create")

    task = db.scalar(
        select(Task).where(
            Task.id == task_id,
            Task.company_id == company_id,
        )
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    require_agent_use(
        db,
        user,
        company_id=company_id,
        agent_instance_id=task.agent_instance_id,
    )

    if task.mode != "consult":
        raise HTTPException(
            status_code=400,
            detail="Task mode must be 'consult'. Create task with mode=consult.",
        )

    try:
        task = run_consultation(
            db,
            company_id=company_id,
            task_id=task_id,
            user_id=user.id,
            check_scope=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return task


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

    existing = db.scalar(
        select(Approval).where(
            Approval.id == approval_id,
            Approval.company_id == company_id,
        )
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Approval not found")

    require_agent_approve(
        db,
        user,
        company_id=company_id,
        agent_instance_id=existing.agent_instance_id,
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

    existing = db.scalar(
        select(Approval).where(
            Approval.id == approval_id,
            Approval.company_id == company_id,
        )
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Approval not found")

    require_agent_approve(
        db,
        user,
        company_id=company_id,
        agent_instance_id=existing.agent_instance_id,
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
