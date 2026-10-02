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


class HireAgentRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)


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
