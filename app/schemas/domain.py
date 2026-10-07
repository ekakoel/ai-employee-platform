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


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    company_id: str
    agent_instance_id: str
    title: str
    instruction: str
    status: str
    result: str | None
    created_at: datetime


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
