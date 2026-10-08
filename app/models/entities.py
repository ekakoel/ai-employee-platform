from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def new_id() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class TaskStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class UserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"

class DocumentStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"

class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ExperienceStatus(str, Enum):
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class DelegationStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AutomationTriggerType(str, Enum):
    SCHEDULE = "schedule"
    EVENT = "event"


class AutomationRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED_APPROVAL = "paused_approval"
    CANCELLED = "cancelled"

class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    agent_instances: Mapped[list["AgentInstance"]] = relationship(back_populates="company")
    knowledge_items: Mapped[list["KnowledgeItem"]] = relationship(back_populates="company")
    tasks: Mapped[list["Task"]] = relationship(back_populates="company")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="company")
    subscriptions: Mapped[list["AgentSubscription"]] = relationship(back_populates="company", cascade="all, delete-orphan")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    permissions: Mapped[list["Permission"]] = relationship(secondary="role_permissions", back_populates="roles")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    roles: Mapped[list[Role]] = relationship(secondary="role_permissions", back_populates="permissions")


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)

    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[str] = mapped_column(ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True)



class Department(Base):
    """Company organizational unit (Job 18)."""

    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_company_department_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    company: Mapped[Company] = relationship()
    users: Mapped[list["User"]] = relationship(back_populates="department")


class AgentTeam(Base):
    """Named group of AI employees within a company (Job 18)."""

    __tablename__ = "agent_teams"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_company_agent_team_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    department_id: Mapped[str | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    company: Mapped[Company] = relationship()
    members: Mapped[list["AgentTeamMember"]] = relationship(
        back_populates="team",
        cascade="all, delete-orphan",
    )


class AgentTeamMember(Base):
    """Membership of an agent instance in an AI team."""

    __tablename__ = "agent_team_members"
    __table_args__ = (
        UniqueConstraint(
            "team_id",
            "agent_instance_id",
            name="uq_team_agent_member",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team_id: Mapped[str] = mapped_column(
        ForeignKey("agent_teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_instance_id: Mapped[str] = mapped_column(
        ForeignKey("agent_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    team: Mapped[AgentTeam] = relationship(back_populates="members")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("company_id", "email", name="uq_company_user_email"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"), nullable=False)
    department_id: Mapped[str | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), default=UserStatus.ACTIVE.value, nullable=False)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    company: Mapped[Company] = relationship(back_populates="users")
    role: Mapped[Role] = relationship()
    department: Mapped["Department | None"] = relationship(back_populates="users")


class AgentCatalog(Base):
    """Platform AI Agent Template (published product in the catalog)."""

    __tablename__ = "agent_catalog"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    role: Mapped[str] = mapped_column(String(100), nullable=False)
    skills: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    allowed_tools: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=AgentStatus.ACTIVE.value, nullable=False)

    # Phase 2 — Template fields
    version: Mapped[str] = mapped_column(String(32), default="1.0.0", nullable=False)
    scope: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    responsibilities: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    default_instructions: Mapped[str] = mapped_column(Text, default="", nullable=False)
    default_knowledge_requirements: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    default_policies: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    default_approval_recommendations: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    default_autonomy: Mapped[str] = mapped_column(String(10), default="1", nullable=False)
    evaluation_criteria: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    changelog: Mapped[str] = mapped_column(Text, default="", nullable=False)

    instances: Mapped[list["AgentInstance"]] = relationship(back_populates="catalog")
    subscriptions: Mapped[list["AgentSubscription"]] = relationship(back_populates="catalog")


class AgentSubscription(Base):
    __tablename__ = "agent_subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    catalog_agent_id: Mapped[str] = mapped_column(ForeignKey("agent_catalog.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default=SubscriptionStatus.ACTIVE.value, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped[Company] = relationship(back_populates="subscriptions")
    catalog: Mapped[AgentCatalog] = relationship(back_populates="subscriptions")
    agent_instances: Mapped[list["AgentInstance"]] = relationship(back_populates="subscription")


class AgentInstance(Base):
    __tablename__ = "agent_instances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    catalog_agent_id: Mapped[str] = mapped_column(ForeignKey("agent_catalog.id"), nullable=False, index=True)
    subscription_id: Mapped[str] = mapped_column(ForeignKey("agent_subscriptions.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=AgentStatus.ACTIVE.value, nullable=False)
    configuration: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Phase 2 — snapshot of template at hire time + company customization
    template_version: Mapped[str] = mapped_column(String(32), default="1.0.0", nullable=False)
    instructions: Mapped[str] = mapped_column(Text, default="", nullable=False)
    skills: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    allowed_tools: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    scope: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    autonomy: Mapped[str] = mapped_column(String(10), default="1", nullable=False)
    policies: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Phase 3 — primary human supervisor
    supervisor_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    # Job 18 — optional department ownership
    department_id: Mapped[str | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    company: Mapped[Company] = relationship(back_populates="agent_instances")
    catalog: Mapped[AgentCatalog] = relationship(back_populates="instances")
    subscription: Mapped["AgentSubscription"] = relationship(back_populates="agent_instances")
    tasks: Mapped[list["Task"]] = relationship(back_populates="agent_instance")
    access_grants: Mapped[list["AgentAccess"]] = relationship(
        back_populates="agent_instance",
        cascade="all, delete-orphan",
    )


class AgentAccess(Base):
    """Per-agent human access: use / manage / approve / supervisor."""

    __tablename__ = "agent_access"
    __table_args__ = (
        UniqueConstraint(
            "agent_instance_id",
            "user_id",
            name="uq_agent_user_access",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_instance_id: Mapped[str] = mapped_column(
        ForeignKey("agent_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    can_use: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    can_manage: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_approve: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_supervisor: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    agent_instance: Mapped["AgentInstance"] = relationship(back_populates="access_grants")
    user: Mapped["User"] = relationship()
    company: Mapped["Company"] = relationship()



class Skill(Base):
    """Reusable professional capability (platform or company-scoped)."""

    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    objective: Mapped[str] = mapped_column(Text, default="", nullable=False)
    instructions: Mapped[str] = mapped_column(Text, default="", nullable=False)
    required_knowledge: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    allowed_tools: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    workflow: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    evaluation_criteria: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    version: Mapped[str] = mapped_column(String(32), default="1.0.0", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    assignments: Mapped[list["AgentSkill"]] = relationship(
        back_populates="skill",
        cascade="all, delete-orphan",
    )


class AgentSkill(Base):
    """Assignment of a Skill to an Agent Instance."""

    __tablename__ = "agent_skills"
    __table_args__ = (
        UniqueConstraint(
            "agent_instance_id",
            "skill_id",
            name="uq_agent_skill",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_instance_id: Mapped[str] = mapped_column(
        ForeignKey("agent_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    skill_id: Mapped[str] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    skill: Mapped["Skill"] = relationship(back_populates="assignments")
    agent_instance: Mapped["AgentInstance"] = relationship()


class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    agent_instance_id: Mapped[str | None] = mapped_column(ForeignKey("agent_instances.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), default="general", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    company: Mapped[Company] = relationship(back_populates="knowledge_items")

class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=new_id,
    )

    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )

    agent_instance_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_instances.id"),
        nullable=True,
        index=True,
    )

    original_filename: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    stored_filename: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    content_type: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    file_size: Mapped[int] = mapped_column(
        nullable=False,
    )

    status: Mapped[DocumentStatus] = mapped_column(
        default=DocumentStatus.UPLOADED,
        nullable=False,
    )

    extracted_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    company: Mapped[Company] = relationship()

    agent_instance: Mapped[AgentInstance | None] = relationship()
    

class KnowledgeChunk(Base):
    """Chunk of knowledge for retrieval (from item or document)."""

    __tablename__ = "knowledge_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_instance_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_instances.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    knowledge_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_items.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    knowledge_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(default=0, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_estimate: Mapped[int] = mapped_column(default=0, nullable=False)
    # Job 26 — vector embedding (JSON list[float]; SQLite-safe, pgvector optional later)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class AgentMemory(Base):
    """
    Agent-scoped contextual memory with lifecycle controls.

    Distinct from company Knowledge and from Experience (Phase 7).
    """

    __tablename__ = "agent_memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_instance_id: Mapped[str] = mapped_column(
        ForeignKey("agent_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), default="context", nullable=False)
    source_task_id: Mapped[str | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )



class Experience(Base):
    """
    Controlled learning record — never auto-changes policy or permissions.

    Lifecycle: candidate -> validated | rejected -> archived
    """

    __tablename__ = "experiences"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_instance_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_instances.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_task_id: Mapped[str | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    situation: Mapped[str] = mapped_column(Text, default="", nullable=False)
    context: Mapped[str] = mapped_column(Text, default="", nullable=False)
    problem: Mapped[str] = mapped_column(Text, default="", nullable=False)
    decision: Mapped[str] = mapped_column(Text, default="", nullable=False)
    action: Mapped[str] = mapped_column(Text, default="", nullable=False)
    result: Mapped[str] = mapped_column(Text, default="", nullable=False)
    human_correction: Mapped[str] = mapped_column(Text, default="", nullable=False)
    lesson: Mapped[str] = mapped_column(Text, default="", nullable=False)
    confidence: Mapped[float] = mapped_column(default=0.5, nullable=False)
    validation_status: Mapped[str] = mapped_column(
        String(30),
        default=ExperienceStatus.CANDIDATE.value,
        nullable=False,
        index=True,
    )
    validated_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    success_count: Mapped[int] = mapped_column(default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )



class DelegationRequest(Base):
    """
    Structured inter-agent delegation request (Job 08).

    Execution/propagation is Job 09; this record validates target
    and captures the capability contract.
    """

    __tablename__ = "delegation_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_agent_instance_id: Mapped[str] = mapped_column(
        ForeignKey("agent_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_agent_instance_id: Mapped[str] = mapped_column(
        ForeignKey("agent_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requested_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    capability: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        default=DelegationStatus.PENDING.value,
        nullable=False,
        index=True,
    )
    validation_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Job 09 — execution fields
    child_task_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    timeout_seconds: Mapped[int] = mapped_column(default=300, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )



class AutomationRule(Base):
    """Scheduled or event-driven automation that creates agent tasks."""

    __tablename__ = "automation_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_instance_id: Mapped[str] = mapped_column(
        ForeignKey("agent_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    trigger_type: Mapped[str] = mapped_column(
        String(30),
        default=AutomationTriggerType.SCHEDULE.value,
        nullable=False,
        index=True,
    )
    # schedule: interval_seconds between runs; next_run_at is the due clock
    interval_seconds: Mapped[int | None] = mapped_column(nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    # event: fire when this event_type is posted
    event_type: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    task_title_template: Mapped[str] = mapped_column(String(300), nullable=False)
    task_instruction_template: Mapped[str] = mapped_column(Text, nullable=False)
    task_mode: Mapped[str] = mapped_column(String(20), default="consult", nullable=False)
    max_retries: Mapped[int] = mapped_column(default=3, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class AutomationRun(Base):
    """One execution attempt of an automation rule (idempotent)."""

    __tablename__ = "automation_runs"
    __table_args__ = (
        UniqueConstraint("company_id", "idempotency_key", name="uq_automation_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_id: Mapped[str] = mapped_column(
        ForeignKey("automation_rules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    attempt: Mapped[int] = mapped_column(default=1, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        default=AutomationRunStatus.PENDING.value,
        nullable=False,
        index=True,
    )
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    agent_instance_id: Mapped[str] = mapped_column(ForeignKey("agent_instances.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    # execute = may run tools; consult = recommendation only (no side-effect tools)
    mode: Mapped[str] = mapped_column(String(20), default="execute", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default=TaskStatus.PENDING.value, nullable=False)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    company: Mapped[Company] = relationship(back_populates="tasks")
    agent_instance: Mapped[AgentInstance] = relationship(back_populates="tasks")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    agent_instance_id: Mapped[str | None] = mapped_column(ForeignKey("agent_instances.id"), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(150), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    company: Mapped[Company] = relationship(back_populates="audit_logs")




class NotificationType(str, Enum):
    APPROVAL_REQUESTED = "approval.requested"
    DELEGATION_RECEIVED = "delegation.received"
    TASK_FAILED = "task.failed"
    TASK_COMPLETED = "task.completed"
    SCOPE_MISS = "scope.miss"
    SYSTEM = "system"


class Notification(Base):
    """User-targeted in-app notification (Job 20)."""

    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )

    company: Mapped[Company] = relationship()
    user: Mapped[User] = relationship()



class ConversationStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    CLOSED = "closed"


class MessageRole(str, Enum):
    HUMAN = "human"
    AGENT = "agent"
    SYSTEM = "system"


class Conversation(Base):
    """Human ↔ Agent chat thread (Job 21). No tools without Task."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_instance_id: Mapped[str] = mapped_column(
        ForeignKey("agent_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        default=ConversationStatus.ACTIVE.value,
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(Base):
    """Single chat message in a Conversation."""

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Optional link when human requests execution via task
    task_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")



class Plan(Base):
    """SaaS plan with quota limits (Job 22)."""

    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    max_agents: Mapped[int] = mapped_column(default=5, nullable=False)
    max_tasks_day: Mapped[int] = mapped_column(default=100, nullable=False)
    max_automations: Mapped[int] = mapped_column(default=10, nullable=False)
    max_llm_calls_day: Mapped[int] = mapped_column(default=500, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class CompanyPlanSubscription(Base):
    """Company assigned to a Plan."""

    __tablename__ = "company_plan_subscriptions"
    __table_args__ = (
        UniqueConstraint("company_id", name="uq_company_plan_sub"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("plans.id"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    plan: Mapped[Plan] = relationship()
    company: Mapped[Company] = relationship()


class UsageCounter(Base):
    """Daily usage counters per company (Job 22)."""

    __tablename__ = "usage_counters"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "metric",
            "period_date",
            name="uq_usage_company_metric_day",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metric: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    period_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    count: Mapped[int] = mapped_column(default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )



class WorkflowRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED_APPROVAL = "paused_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowDefinition(Base):
    """Ordered multi-step automation workflow (Job 27)."""

    __tablename__ = "workflow_definitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # ordered list of steps: {type, ...params}
    steps: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class WorkflowRun(Base):
    """One execution of a WorkflowDefinition."""

    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    definition_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default=WorkflowRunStatus.PENDING.value,
        nullable=False,
        index=True,
    )
    current_step: Mapped[int] = mapped_column(default=0, nullable=False)
    context: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    step_results: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )



class LLMUsage(Base):
    """Per-call LLM token / cost record (Job 28)."""

    __tablename__ = "llm_usage"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_instance_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    model: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(default=0.0, nullable=False)
    provider: Mapped[str] = mapped_column(String(50), default="ollama", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )



class IntegrationStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"


class Integration(Base):
    """External system connection for company (Job 29)."""

    __tablename__ = "integrations"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_company_integration_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # Opaque config JSON (secrets should be written via service encrypt helper)
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # Webhook shared secret (stored hashed)
    webhook_secret_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Maps inbound event names → automation event_type
    event_map: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        default=IntegrationStatus.ACTIVE.value,
        nullable=False,
        index=True,
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

class Policy(Base):
    __tablename__ = "policies"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=new_id,
    )

    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )

    configuration: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    company: Mapped[Company] = relationship()


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=new_id,
    )

    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    task_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    agent_instance_id: Mapped[str] = mapped_column(
        ForeignKey("agent_instances.id"),
        nullable=False,
        index=True,
    )

    action: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    reason: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )

    payload: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default=ApprovalStatus.PENDING.value,
        nullable=False,
        index=True,
    )

    reviewed_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    review_comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    company: Mapped[Company] = relationship()