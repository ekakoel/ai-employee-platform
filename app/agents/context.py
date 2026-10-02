from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AgentInstance, KnowledgeItem


@dataclass
class AgentContext:
    agent_instance_id: str
    company_id: str
    name: str
    status: str
    configuration: dict
    knowledge: list[dict] = field(default_factory=list)


def load_agent_context(
    db: Session,
    *,
    company_id: str,
    agent_instance_id: str,
) -> AgentContext:
    agent = db.scalar(
        select(AgentInstance).where(
            AgentInstance.id == agent_instance_id,
            AgentInstance.company_id == company_id,
        )
    )

    if agent is None:
        raise ValueError(
            "Agent instance not found for this company."
        )

    knowledge_items = list(
        db.scalars(
            select(KnowledgeItem)
            .where(
                KnowledgeItem.company_id == company_id,
                KnowledgeItem.agent_instance_id == agent_instance_id,
                KnowledgeItem.is_active.is_(True),
            )
            .order_by(KnowledgeItem.created_at.asc())
        ).all()
    )

    return AgentContext(
        agent_instance_id=agent.id,
        company_id=agent.company_id,
        name=agent.name,
        status=agent.status,
        configuration=agent.configuration or {},
        knowledge=[
            {
                "id": item.id,
                "title": item.title,
                "content": item.content,
                "category": item.category,
            }
            for item in knowledge_items
        ],
    )