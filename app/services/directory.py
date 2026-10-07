"""Job 08 — Agent Directory: capabilities, discovery, target validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AgentCatalog, AgentInstance, AgentStatus, Skill
from app.services.skills import load_assigned_skills


@dataclass
class AgentCapabilityCard:
    agent_instance_id: str
    name: str
    status: str
    role: str
    skills: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    scope: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    catalog_slug: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_instance_id": self.agent_instance_id,
            "name": self.name,
            "status": self.status,
            "role": self.role,
            "skills": list(self.skills),
            "tools": list(self.tools),
            "scope": list(self.scope),
            "capabilities": list(self.capabilities),
            "catalog_slug": self.catalog_slug,
        }


def build_capabilities(
    *,
    role: str,
    skills: list[str],
    tools: list[str],
    scope: list[str],
    skill_slugs: list[str] | None = None,
) -> list[str]:
    """
    Derive a flat capability registry for an agent.

    Capabilities are searchable keys used for discovery/delegation.
    """
    caps: list[str] = []
    if role:
        caps.append(f"role:{role.lower().replace(' ', '_')}")
    for s in skills or []:
        caps.append(f"skill:{str(s).lower()}")
    for s in skill_slugs or []:
        key = f"skill:{str(s).lower()}"
        if key not in caps:
            caps.append(key)
    for t in tools or []:
        caps.append(f"tool:{str(t).lower()}")
    for sc in scope or []:
        caps.append(f"scope:{str(sc).lower()}")
    # de-dupe preserve order
    return list(dict.fromkeys(caps))


def agent_capability_card(
    db: Session,
    agent: AgentInstance,
) -> AgentCapabilityCard:
    catalog = db.get(AgentCatalog, agent.catalog_agent_id)
    role = catalog.role if catalog else ""
    slug = catalog.slug if catalog else None

    skills = list(agent.skills or [])
    tools = list(agent.allowed_tools or [])
    scope = list(agent.scope or [])

    formal = load_assigned_skills(
        db,
        company_id=agent.company_id,
        agent_instance_id=agent.id,
    )
    skill_slugs = [s.slug for s in formal]
    for s in skill_slugs:
        if s not in skills:
            skills.append(s)

    caps = build_capabilities(
        role=role,
        skills=skills,
        tools=tools,
        scope=scope,
        skill_slugs=skill_slugs,
    )

    return AgentCapabilityCard(
        agent_instance_id=agent.id,
        name=agent.name,
        status=agent.status,
        role=role,
        skills=skills,
        tools=tools,
        scope=scope,
        capabilities=caps,
        catalog_slug=slug,
    )


def list_directory(
    db: Session,
    *,
    company_id: str,
    active_only: bool = True,
) -> list[AgentCapabilityCard]:
    q = select(AgentInstance).where(AgentInstance.company_id == company_id)
    if active_only:
        q = q.where(AgentInstance.status == AgentStatus.ACTIVE.value)
    agents = list(db.scalars(q).all())
    return [agent_capability_card(db, a) for a in agents]


def discover_agents(
    db: Session,
    *,
    company_id: str,
    capability: str | None = None,
    skill: str | None = None,
    tool: str | None = None,
    role: str | None = None,
    exclude_agent_id: str | None = None,
) -> list[AgentCapabilityCard]:
    cards = list_directory(db, company_id=company_id, active_only=True)
    results = []
    for card in cards:
        if exclude_agent_id and card.agent_instance_id == exclude_agent_id:
            continue
        caps_lower = [c.lower() for c in card.capabilities]
        if capability:
            needle = capability.lower()
            # match full key or bare skill/tool name
            if not any(
                needle == c
                or c.endswith(":" + needle)
                or needle in c
                for c in caps_lower
            ):
                continue
        if skill:
            s = skill.lower()
            if f"skill:{s}" not in caps_lower and s not in [
                x.lower() for x in card.skills
            ]:
                continue
        if tool:
            t = tool.lower()
            if f"tool:{t}" not in caps_lower and t not in [
                x.lower() for x in card.tools
            ]:
                continue
        if role:
            r = role.lower().replace(" ", "_")
            if f"role:{r}" not in caps_lower and r not in card.role.lower().replace(
                " ", "_"
            ):
                continue
        results.append(card)
    return results


@dataclass
class TargetValidation:
    valid: bool
    reason: str
    target: AgentCapabilityCard | None = None
    matched_capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "reason": self.reason,
            "target": self.target.to_dict() if self.target else None,
            "matched_capabilities": list(self.matched_capabilities),
        }


def validate_delegation_target(
    db: Session,
    *,
    company_id: str,
    target_agent_instance_id: str,
    required_capability: str | None = None,
    source_agent_instance_id: str | None = None,
) -> TargetValidation:
    """
    Validate that the target agent exists in the company, is active,
    is not the source, and optionally holds the required capability.
    """
    agent = db.scalar(
        select(AgentInstance).where(
            AgentInstance.id == target_agent_instance_id,
            AgentInstance.company_id == company_id,
        )
    )
    if agent is None:
        return TargetValidation(
            valid=False,
            reason="Target agent not found in this company.",
        )

    if agent.status != AgentStatus.ACTIVE.value:
        return TargetValidation(
            valid=False,
            reason=f"Target agent is not active (status={agent.status}).",
        )

    if (
        source_agent_instance_id
        and source_agent_instance_id == target_agent_instance_id
    ):
        return TargetValidation(
            valid=False,
            reason="Source and target agent must be different.",
        )

    card = agent_capability_card(db, agent)
    matched: list[str] = []

    if required_capability:
        needle = required_capability.lower()
        for c in card.capabilities:
            cl = c.lower()
            if needle == cl or cl.endswith(":" + needle) or needle in cl:
                matched.append(c)
        if not matched:
            return TargetValidation(
                valid=False,
                reason=(
                    f"Target agent does not provide capability "
                    f"'{required_capability}'."
                ),
                target=card,
                matched_capabilities=[],
            )

    return TargetValidation(
        valid=True,
        reason="Target agent is valid for delegation.",
        target=card,
        matched_capabilities=matched,
    )
