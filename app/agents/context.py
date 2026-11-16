
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
    assigned_skills: list[dict[str, Any]] = field(default_factory=list)
    memories: list[dict[str, Any]] = field(default_factory=list)
    retrieved_knowledge: list[dict[str, Any]] = field(default_factory=list)
    experiences: list[dict[str, Any]] = field(default_factory=list)

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
            "skills_detail": list(self.assigned_skills),
            "memories": list(self.memories),
            "retrieved_knowledge": list(self.retrieved_knowledge),
            "experiences": list(self.experiences),
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
    if not agent.company.is_active:
        raise ValueError("Agent company is not active.")
    if agent.status != "active":
        raise ValueError("Agent instance is not active.")
    if agent.subscription is not None and agent.subscription.status != "active":
        raise ValueError("Agent subscription is not active.")

    if task is not None:
        if task.company_id != agent.company_id:
            raise ValueError(
                "Task does not belong to the agent company."
            )

        if task.agent_instance_id != agent.id:
            raise ValueError(
                "Task does not belong to the agent instance."
            )
        from app.services.grounding import general_reply
        from app.services.scope_guard import check_scope

        if not general_reply(task.instruction or ""):
            match = check_scope(db, company_id=agent.company_id, agent=agent, instruction=task.instruction or task.title or "")
            if not match.in_scope:
                raise ValueError("Request is outside the assigned employee scope.")

    # Direct company-wide knowledge loading bypasses source grants. All knowledge
    # is now supplied only by the authorization-filtered retrieval path below.
    knowledge_items = []

    # AgentInstance defines the relationship as `catalog`.
    catalog = agent.catalog

    # Prefer instance snapshot (pinned at hire); fall back to catalog.
    instance_skills = list(agent.skills or [])
    catalog_skills = list(catalog.skills or []) if catalog else []

    skills = instance_skills if instance_skills else catalog_skills
    from app.services.grounding import authorized_tools
    allowed_tools = authorized_tools(agent)

    # Phase 4: formal Skill assignments enrich instructions and tools
    from app.services.skills import load_assigned_skills, skill_tool_union

    formal_skills = load_assigned_skills(
        db,
        company_id=agent.company_id,
        agent_instance_id=agent.id,
    )
    skill_tools = skill_tool_union(formal_skills)
    # Tool requirement: agent may use tools in its allow-list;
    # skill tools that are also on the agent allow-list are emphasized.
    # Skills cannot grant tools outside agent allowed_tools (security).
    if formal_skills:
        allowed_tools = [name for name in allowed_tools if name in skill_tools]

    skill_slugs = [s.slug for s in formal_skills]
    if skill_slugs:
        # merge formal skill slugs into skills list for runtime visibility
        merged = list(dict.fromkeys(list(skills) + skill_slugs))
        skills = merged

    assigned_skills = [
        {
            "id": s.id,
            "slug": s.slug,
            "name": s.name,
            "objective": s.objective,
            "instructions": s.instructions,
            "workflow": s.workflow,
            "required_knowledge": s.required_knowledge,
            "allowed_tools": list(s.allowed_tools or []),
            "version": s.version,
        }
        for s in formal_skills
    ]

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

    from app.knowledge.retrieval import (
        active_agent_memories,
        search_knowledge_chunks,
    )

    # AgentMemory has no source-level read grants yet; fail closed instead of
    # injecting unclassified memory into the model context.
    memories = []

    retrieved_knowledge: list[dict[str, Any]] = []
    experiences: list[dict[str, Any]] = []
    if task is not None and task.instruction:
        query = f"{task.title or ''} {task.instruction}"
        retrieved_knowledge = search_knowledge_chunks(
            db,
            company_id=agent.company_id,
            agent_instance_id=agent.id,
            requester_id=task.requested_by_user_id,
            purpose="task_execution",
            task_id=task.id,
            query=query,
            limit=5,
        )
        # Validated experiences also lack source-read grants. Keep them out of
        # context until the same policy model is applied to that data family.
        experiences = []

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
        assigned_skills=assigned_skills,
        memories=memories,
        retrieved_knowledge=retrieved_knowledge,
        experiences=experiences,
    )
