
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import AgentInstance, KnowledgeItem, Task


@dataclass(frozen=True)
class AgentContext:
    """
    Runtime context provided to an AI Employee.

    The LLM receives this normalized context instead of
    accessing SQLAlchemy models or the database directly.
    """

    company_id: str
    company_name: str

    agent_instance_id: str
    agent_name: str

    agent_role: str
    skills: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)

    task_id: str | None = None
    task_title: str | None = None
    task_instruction: str | None = None

    knowledge: list[dict[str, Any]] = field(default_factory=list)

    configuration: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "company": {
                "id": self.company_id,
                "name": self.company_name,
            },
            "agent": {
                "id": self.agent_instance_id,
                "name": self.agent_name,
                "role": self.agent_role,
                "skills": list(self.skills),
                "allowed_tools": list(self.allowed_tools),
            },
            "task": {
                "id": self.task_id,
                "title": self.task_title,
                "instruction": self.task_instruction,
            },
            "knowledge": list(self.knowledge),
            "configuration": dict(self.configuration),
        }


def load_agent_context(
    db: Session,
    agent: AgentInstance,
    task: Task | None = None,
) -> AgentContext:
    """
    Build a normalized AgentContext from database entities.

    This function enforces company ownership before exposing
    knowledge to the AI Employee.
    """

    if agent.company is None:
        raise ValueError("Agent instance has no company.")

    if task is not None:
        if task.company_id != agent.company_id:
            raise ValueError(
                "Task does not belong to the agent company."
            )

        if task.agent_instance_id != agent.id:
            raise ValueError(
                "Task does not belong to the agent instance."
            )

    knowledge_query = db.query(KnowledgeItem).filter(
        KnowledgeItem.company_id == agent.company_id,
        KnowledgeItem.is_active.is_(True),
    )

    knowledge_items = knowledge_query.filter(
        (KnowledgeItem.agent_instance_id.is_(None))
        | (KnowledgeItem.agent_instance_id == agent.id)
    ).all()

    # AgentInstance defines the relationship as `catalog`.
    catalog = agent.catalog

    # Prefer instance snapshot (pinned at hire); fall back to catalog.
    instance_skills = list(agent.skills or [])
    instance_tools = list(agent.allowed_tools or [])
    catalog_skills = list(catalog.skills or []) if catalog else []
    catalog_tools = list(catalog.allowed_tools or []) if catalog else []

    skills = instance_skills if instance_skills else catalog_skills
    allowed_tools = instance_tools if instance_tools else catalog_tools

    configuration = dict(agent.configuration or {})
    if agent.instructions:
        configuration.setdefault("instructions", agent.instructions)
    if agent.scope:
        configuration.setdefault("scope", list(agent.scope))
    if agent.autonomy:
        configuration.setdefault("autonomy", agent.autonomy)
    if agent.policies:
        configuration.setdefault("policies", dict(agent.policies))
    if agent.template_version:
        configuration.setdefault("template_version", agent.template_version)

    return AgentContext(
        company_id=agent.company_id,
        company_name=agent.company.name,
        agent_instance_id=agent.id,
        agent_name=agent.name,
        agent_role=catalog.role if catalog else "",
        skills=skills,
        allowed_tools=allowed_tools,
        task_id=task.id if task else None,
        task_title=task.title if task else None,
        task_instruction=task.instruction if task else None,
        knowledge=[
            {
                "id": item.id,
                "title": item.title,
                "content": item.content,
                "category": item.category,
            }
            for item in knowledge_items
        ],
        configuration=configuration,
    )
