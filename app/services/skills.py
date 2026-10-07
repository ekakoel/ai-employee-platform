"""Phase 4 — Skill catalog and agent assignment."""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.entities import AgentSkill, Skill


def list_available_skills(db: Session, company_id: str) -> list[Skill]:
    """Platform skills (company_id IS NULL) + company custom skills."""
    return list(
        db.scalars(
            select(Skill).where(
                Skill.is_active.is_(True),
                or_(
                    Skill.company_id.is_(None),
                    Skill.company_id == company_id,
                ),
            ).order_by(Skill.slug)
        ).all()
    )


def get_skill_for_company(
    db: Session,
    *,
    skill_id: str,
    company_id: str,
) -> Skill | None:
    skill = db.get(Skill, skill_id)
    if not skill or not skill.is_active:
        return None
    if skill.company_id is None:
        return skill
    if skill.company_id == company_id:
        return skill
    return None


def assign_skill(
    db: Session,
    *,
    company_id: str,
    agent_instance_id: str,
    skill_id: str,
) -> AgentSkill:
    existing = db.scalar(
        select(AgentSkill).where(
            AgentSkill.agent_instance_id == agent_instance_id,
            AgentSkill.skill_id == skill_id,
        )
    )
    if existing:
        return existing
    row = AgentSkill(
        company_id=company_id,
        agent_instance_id=agent_instance_id,
        skill_id=skill_id,
    )
    db.add(row)
    db.flush()
    return row


def list_agent_skills(
    db: Session,
    *,
    company_id: str,
    agent_instance_id: str,
) -> list[AgentSkill]:
    return list(
        db.scalars(
            select(AgentSkill).where(
                AgentSkill.company_id == company_id,
                AgentSkill.agent_instance_id == agent_instance_id,
            )
        ).all()
    )


def load_assigned_skills(
    db: Session,
    *,
    company_id: str,
    agent_instance_id: str,
) -> list[Skill]:
    assignments = list_agent_skills(
        db, company_id=company_id, agent_instance_id=agent_instance_id
    )
    skills: list[Skill] = []
    for a in assignments:
        skill = db.get(Skill, a.skill_id)
        if skill and skill.is_active:
            if skill.company_id is None or skill.company_id == company_id:
                skills.append(skill)
    return skills


def skill_tool_union(skills: list[Skill]) -> set[str]:
    tools: set[str] = set()
    for s in skills:
        tools.update(s.allowed_tools or [])
    return tools
