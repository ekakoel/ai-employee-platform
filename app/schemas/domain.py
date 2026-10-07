from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CompanyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    created_at: datetime


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    role: str = Field(default="manager", min_length=2, max_length=100)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    company_id: str
    name: str
    email: str
    role_id: str
    status: str
    created_at: datetime


class AgentCatalogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    slug: str
    name: str
    description: str
    role: str
    skills: list
    allowed_tools: list
    status: str
    version: str = "1.0.0"
    scope: list = []
    responsibilities: list = []
    default_instructions: str = ""
    default_knowledge_requirements: list = []
    default_policies: dict = {}
    default_approval_recommendations: dict = {}
    default_autonomy: str = "1"
    evaluation_criteria: list = []
    is_published: bool = True
    published_at: datetime | None = None
    changelog: str = ""


class HireAgentRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)


class AgentInstanceUpdate(BaseModel):
    """Company customization of a hired Agent Instance."""

    name: str | None = Field(default=None, min_length=2, max_length=200)
    instructions: str | None = None
    autonomy: str | None = Field(default=None, pattern="^[0-3]$")
    policies: dict | None = None


class AgentSubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    company_id: str
    catalog_agent_id: str
    status: str
    started_at: datetime
    cancelled_at: datetime | None


class AgentInstanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    company_id: str
    catalog_agent_id: str
    subscription_id: str
    name: str
    status: str
    configuration: dict
    created_at: datetime
    template_version: str = "1.0.0"
    instructions: str = ""
    skills: list = []
    allowed_tools: list = []
    scope: list = []
    autonomy: str = "1"
    policies: dict = {}
    supervisor_user_id: str | None = None


class AgentAccessCreate(BaseModel):
    user_id: str
    can_use: bool = True
    can_manage: bool = False
    can_approve: bool = False
    is_supervisor: bool = False


class AgentAccessUpdate(BaseModel):
    can_use: bool | None = None
    can_manage: bool | None = None
    can_approve: bool | None = None
    is_supervisor: bool | None = None


class AgentAccessRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    company_id: str
    agent_instance_id: str
    user_id: str
    can_use: bool
    can_manage: bool
    can_approve: bool
    is_supervisor: bool
    created_at: datetime


class KnowledgeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1)
    category: str = Field(default="general", max_length=100)
    agent_instance_id: str | None = None


class KnowledgeUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    content: str | None = None
    category: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None


class KnowledgeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    company_id: str
    agent_instance_id: str | None
    title: str
    content: str
    category: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

class KnowledgeDocumentRead(BaseModel):
    id: str
    company_id: str
    agent_instance_id: str | None
    original_filename: str
    stored_filename: str
    content_type: str
    file_size: int
    status: str
    extracted_text: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

class TaskCreate(BaseModel):
    agent_instance_id: str
    title: str = Field(min_length=1, max_length=300)
    instruction: str = Field(min_length=1)
    mode: str = Field(default="execute", pattern="^(execute|consult)$")


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    company_id: str
    agent_instance_id: str
    title: str
    instruction: str
    mode: str = "execute"
    status: str
    result: str | None
    created_at: datetime


class ConsultationResult(BaseModel):
    mode: str = "consult"
    recommendation: str
    rationale: str
    expected_impact: str = ""
    alternatives: list[str] = []
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    side_effects_executed: bool = False
    retrieved_knowledge_count: int = 0
    experience_count: int = 0
    notes: str = "Consultation mode: no side-effect tools were executed."


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    company_id: str
    user_id: str | None
    agent_instance_id: str | None
    task_id: str | None
    action: str
    resource_type: str
    resource_id: str | None
    status: str
    details: dict
    created_at: datetime


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    task_id: str
    agent_instance_id: str
    action: str
    reason: str
    payload: dict
    status: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    review_comment: str | None
    created_at: datetime


class ApprovalReviewRequest(BaseModel):
    comment: str | None = Field(
        default=None,
        max_length=2000,
    )

class SkillCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=100)
    name: str = Field(min_length=2, max_length=200)
    description: str = ""
    objective: str = ""
    instructions: str = ""
    required_knowledge: list = []
    allowed_tools: list = []
    workflow: list = []
    evaluation_criteria: list = []
    version: str = "1.0.0"


class SkillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    company_id: str | None
    slug: str
    name: str
    description: str
    objective: str
    instructions: str
    required_knowledge: list
    allowed_tools: list
    workflow: list
    evaluation_criteria: list
    version: str
    is_active: bool
    created_at: datetime


class AgentSkillAssign(BaseModel):
    skill_id: str


class AgentSkillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    company_id: str
    agent_instance_id: str
    skill_id: str
    created_at: datetime


class PolicyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str = ""
    # configuration: {tool, effect, conditions, approval_level, priority}
    configuration: dict = Field(default_factory=dict)
    is_active: bool = True


class PolicyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = None
    configuration: dict | None = None
    is_active: bool | None = None


class PolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    company_id: str
    name: str
    description: str
    configuration: dict
    is_active: bool
    created_at: datetime
    updated_at: datetime


class KnowledgeChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    company_id: str
    agent_instance_id: str | None
    knowledge_item_id: str | None
    knowledge_document_id: str | None
    chunk_index: int
    content: str
    token_estimate: int
    is_active: bool
    created_at: datetime


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=20)


class KnowledgeSearchHit(BaseModel):
    id: str
    content: str
    score: float
    source: str
    title: str | None = None
    category: str | None = None
    chunk_index: int | None = None


class AgentMemoryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1)
    category: str = Field(default="context", max_length=100)
    source_task_id: str | None = None
    expires_at: datetime | None = None


class AgentMemoryUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    content: str | None = None
    category: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None
    expires_at: datetime | None = None


class AgentMemoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    company_id: str
    agent_instance_id: str
    title: str
    content: str
    category: str
    source_task_id: str | None
    is_active: bool
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ExperienceCreate(BaseModel):
    """Create experience candidate (optionally linked to a completed task)."""

    source_task_id: str | None = None
    agent_instance_id: str | None = None
    situation: str = ""
    context: str = ""
    problem: str = Field(min_length=1)
    decision: str = ""
    action: str = ""
    result: str = ""
    human_correction: str = ""
    lesson: str = ""
    confidence: float = Field(default=0.4, ge=0.0, le=1.0)


class ExperienceFromTaskRequest(BaseModel):
    decision: str = ""
    action: str = ""
    human_correction: str = ""
    lesson: str = ""
    confidence: float = Field(default=0.4, ge=0.0, le=1.0)


class ExperienceValidateRequest(BaseModel):
    approve: bool
    lesson: str | None = None
    human_correction: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class ExperienceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    company_id: str
    agent_instance_id: str | None
    source_task_id: str | None
    situation: str
    context: str
    problem: str
    decision: str
    action: str
    result: str
    human_correction: str
    lesson: str
    confidence: float
    validation_status: str
    validated_by: str | None
    validated_at: datetime | None
    success_count: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ExperienceSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    agent_instance_id: str | None = None
    limit: int = Field(default=5, ge=1, le=20)
    min_confidence: float = Field(default=0.3, ge=0.0, le=1.0)


class ExperienceSearchHit(BaseModel):
    id: str
    situation: str
    problem: str
    decision: str
    action: str
    result: str
    lesson: str
    human_correction: str
    confidence: float
    score: float
    agent_instance_id: str | None = None
    source_task_id: str | None = None


class AgentDirectoryEntry(BaseModel):
    agent_instance_id: str
    name: str
    status: str
    role: str
    skills: list[str] = []
    tools: list[str] = []
    scope: list[str] = []
    capabilities: list[str] = []
    catalog_slug: str | None = None


class TargetValidationRequest(BaseModel):
    target_agent_instance_id: str
    required_capability: str | None = None
    source_agent_instance_id: str | None = None


class TargetValidationResult(BaseModel):
    valid: bool
    reason: str
    target: AgentDirectoryEntry | None = None
    matched_capabilities: list[str] = []


class DelegationRequestCreate(BaseModel):
    source_agent_instance_id: str
    target_agent_instance_id: str
    capability: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    instruction: str = Field(min_length=1)
    timeout_seconds: int = Field(default=300, ge=1, le=86400)


class DelegationRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    company_id: str
    source_agent_instance_id: str
    target_agent_instance_id: str
    requested_by_user_id: str | None
    capability: str
    title: str
    instruction: str
    status: str
    validation_notes: str
    result: str | None
    child_task_id: str | None = None
    timeout_seconds: int = 300
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DelegationExecuteRequest(BaseModel):
    """Optional overrides when executing a pending/accepted delegation."""
    mode: str = Field(default="consult", pattern="^(execute|consult)$")
    force: bool = False  # ignore soft timeout check only for status transitions


class ExperienceFeedbackRequest(BaseModel):
    """Human feedback after an experience was used or reviewed."""

    helpful: bool
    human_correction: str = ""
    lesson: str | None = None
    confidence_delta: float = Field(default=0.0, ge=-0.5, le=0.5)


class AutomationRuleCreate(BaseModel):
    agent_instance_id: str
    name: str = Field(min_length=2, max_length=200)
    description: str = ""
    trigger_type: str = Field(default="schedule", pattern="^(schedule|event)$")
    interval_seconds: int | None = Field(default=None, ge=1)
    next_run_at: datetime | None = None
    event_type: str | None = Field(default=None, max_length=100)
    task_title_template: str = Field(min_length=1, max_length=300)
    task_instruction_template: str = Field(min_length=1)
    task_mode: str = Field(default="consult", pattern="^(execute|consult)$")
    max_retries: int = Field(default=3, ge=0, le=20)
    is_active: bool = True


class AutomationRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    company_id: str
    agent_instance_id: str
    name: str
    description: str
    trigger_type: str
    interval_seconds: int | None
    next_run_at: datetime | None
    event_type: str | None
    task_title_template: str
    task_instruction_template: str
    task_mode: str
    max_retries: int
    is_active: bool
    last_run_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AutomationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    company_id: str
    rule_id: str
    idempotency_key: str
    attempt: int
    status: str
    task_id: str | None
    error_message: str | None
    trigger_payload: dict
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class AutomationEventRequest(BaseModel):
    event_type: str = Field(min_length=1, max_length=100)
    payload: dict = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=200)


class GovernanceOverview(BaseModel):
    company_id: str
    generated_at: str
    workforce: dict
    tasks: dict
    approvals: dict
    experiences: dict
    automation: dict
    delegation: dict
    audit: dict
