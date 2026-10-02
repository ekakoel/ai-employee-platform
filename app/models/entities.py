from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def new_id() -> str:
    return str(uuid4())


class AgentStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    agent_instances: Mapped[list["AgentInstance"]] = relationship(back_populates="company")
    knowledge_items: Mapped[list["KnowledgeItem"]] = relationship(back_populates="company")
    tasks: Mapped[list["Task"]] = relationship(back_populates="company")


class AgentCatalog(Base):
    __tablename__ = "agent_catalog"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    role: Mapped[str] = mapped_column(String(100), nullable=False)
    skills: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    allowed_tools: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=AgentStatus.ACTIVE.value, nullable=False)

    instances: Mapped[list["AgentInstance"]] = relationship(back_populates="catalog")


class AgentInstance(Base):
    __tablename__ = "agent_instances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    catalog_agent_id: Mapped[str] = mapped_column(ForeignKey("agent_catalog.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=AgentStatus.ACTIVE.value, nullable=False)
    configuration: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    company: Mapped[Company] = relationship(back_populates="agent_instances")
    catalog: Mapped[AgentCatalog] = relationship(back_populates="instances")
    tasks: Mapped[list["Task"]] = relationship(back_populates="agent_instance")


class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    agent_instance_id: Mapped[str | None] = mapped_column(ForeignKey("agent_instances.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), default="general", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    company: Mapped[Company] = relationship(back_populates="knowledge_items")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    agent_instance_id: Mapped[str] = mapped_column(ForeignKey("agent_instances.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default=TaskStatus.PENDING.value, nullable=False)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    company: Mapped[Company] = relationship(back_populates="tasks")
    agent_instance: Mapped[AgentInstance] = relationship(back_populates="tasks")
