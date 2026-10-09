"""Job 38 — Seed demo reservation inventory + knowledge for a company."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import KnowledgeItem, Policy
from app.tools.connectors import get_external_client
from app.services.inventory import upsert_inventory_row


def seed_demo_availability(company_id: str, db: Session | None = None) -> list[dict[str, Any]]:
    """Load Alila-style inventory into the process mock connector."""
    client = get_external_client()
    rows = [
        {
            "id": f"{company_id}-alila-deluxe",
            "company_id": company_id,
            "location": "Alila Hotel",
            "room_type": "Deluxe Double",
            "available": True,
            "capacity": 2,
            "rate": 1_850_000,
            "currency": "IDR",
            "valid_from": "2026-10-01",
            "valid_to": "2026-12-31",
            "notes": "Includes breakfast for 2",
        },
        {
            "id": f"{company_id}-alila-suite",
            "company_id": company_id,
            "location": "Alila Hotel",
            "room_type": "Ocean Suite",
            "available": True,
            "capacity": 3,
            "rate": 3_250_000,
            "currency": "IDR",
            "valid_from": "2026-10-01",
            "valid_to": "2026-12-31",
            "notes": "Suite with living area",
        },
        {
            "id": f"{company_id}-alila-family",
            "company_id": company_id,
            "location": "Alila Hotel",
            "room_type": "Family Room",
            "available": True,
            "capacity": 4,
            "rate": 2_750_000,
            "currency": "IDR",
            "valid_from": "2026-10-01",
            "valid_to": "2026-12-31",
            "notes": "Two queen beds",
        },
        {
            "id": f"{company_id}-city-standard",
            "company_id": company_id,
            "location": "City Hotel",
            "room_type": "Standard Twin",
            "available": True,
            "capacity": 2,
            "rate": 950_000,
            "currency": "IDR",
            "valid_from": "2026-10-01",
            "valid_to": "2026-12-31",
        },
    ]
    created = []
    for row in rows:
        rec = client.create(system="availability", payload=row)
        created.append(rec.payload)
        if db is not None:
            upsert_inventory_row(
                db,
                company_id=company_id,
                system="availability",
                external_key=str(row["id"]),
                payload=row,
            )
    return created


def seed_demo_knowledge(
    db: Session, company_id: str, user_id: str | None = None
) -> KnowledgeItem:
    """Company knowledge snippet so consult/chat can cite hotel facts."""
    title = "Alila Hotel - commercial notes (demo)"
    content = (
        "Property: Alila Hotel (demo inventory).\n"
        "Room types: Deluxe Double (2 pax), Ocean Suite (3 pax), Family Room (4 pax).\n"
        "Rates are net IDR and include breakfast where noted on availability rows.\n"
        "Do not invent rates. Use search_availability for live options, then "
        "draft_quotation or create_reservation only with a verified availability_id.\n"
        "Check-in from 14:00, check-out by 12:00. "
        "Cancellation policy: free until 48h before arrival.\n"
    )
    existing = db.scalar(
        select(KnowledgeItem).where(
            KnowledgeItem.company_id == company_id,
            KnowledgeItem.title == title,
        )
    )
    if existing:
        existing.content = content
        existing.is_active = True
        db.flush()
        return existing
    item = KnowledgeItem(
        company_id=company_id,
        title=title,
        content=content,
        category="reservation",
        is_active=True,
    )
    db.add(item)
    db.flush()
    return item


def seed_demo_policies(db: Session, company_id: str) -> list[str]:
    """Allow common reservation tools so demo tasks are not deny-by-default."""
    specs = [
        ("Allow search_availability", "search_availability", "allow"),
        ("Allow draft_quotation", "draft_quotation", "allow"),
        ("Require approval create_reservation", "create_reservation", "require_approval"),
    ]
    ids: list[str] = []
    for name, tool, effect in specs:
        existing = db.scalar(
            select(Policy).where(
                Policy.company_id == company_id,
                Policy.name == name,
            )
        )
        if existing:
            existing.configuration = {
                "tool": tool,
                "effect": effect,
                "priority": 10,
            }
            existing.is_active = True
            ids.append(existing.id)
            continue
        pol = Policy(
            company_id=company_id,
            name=name,
            description=f"Demo policy for {tool}",
            configuration={"tool": tool, "effect": effect, "priority": 10},
            is_active=True,
        )
        db.add(pol)
        db.flush()
        ids.append(pol.id)
    return ids


def seed_company_reservation_demo(
    db: Session, *, company_id: str, user_id: str | None = None
) -> dict[str, Any]:
    availability = seed_demo_availability(company_id, db=db)
    knowledge = seed_demo_knowledge(db, company_id, user_id=user_id)
    policy_ids = seed_demo_policies(db, company_id)
    return {
        "availability_count": len(availability),
        "availability_ids": [r.get("id") for r in availability],
        "knowledge_id": knowledge.id,
        "knowledge_title": knowledge.title,
        "policy_ids": policy_ids,
    }


def run_reservation_playbook(
    db: Session,
    *,
    company_id: str,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Job 49 — seed inventory + create a pending execute task for availability search.

    Does not execute tools (policy/runtime stay in Task path). Returns task_id for UI.
    """
    from app.models.entities import AgentInstance, Task, TaskStatus

    seed = seed_company_reservation_demo(db, company_id=company_id, user_id=user_id)

    from app.models.entities import AgentCatalog, AgentSubscription

    agents = list(
        db.scalars(
            select(AgentInstance).where(
                AgentInstance.company_id == company_id,
                AgentInstance.status == "active",
            )
        ).all()
    )
    agent = None
    hired_now = False
    for a in agents:
        name = (a.name or "").lower()
        scope = " ".join(a.scope or []).lower() if a.scope else ""
        cfg_role = ""
        if isinstance(a.configuration, dict):
            cfg_role = str(a.configuration.get("role") or "").lower()
        if (
            "reservation" in name
            or "reservation" in scope
            or "contract" in name
            or cfg_role == "reservation"
        ):
            agent = a
            break
    if agent is None and agents:
        agent = agents[0]

    # Auto-hire reservation catalog template when company has no agents yet
    if agent is None:
        catalog = db.scalar(
            select(AgentCatalog).where(
                AgentCatalog.slug == "reservation",
                AgentCatalog.status == "active",
            )
        )
        if catalog is None:
            catalog = db.scalar(
                select(AgentCatalog).where(AgentCatalog.is_published == True).limit(1)  # noqa: E712
            )
        if catalog is None:
            return {
                **seed,
                "task_id": None,
                "error": "No agent catalog available. Seed platform catalog first.",
            }
        subscription = AgentSubscription(
            company_id=company_id,
            catalog_agent_id=catalog.id,
        )
        db.add(subscription)
        db.flush()
        skills = list(catalog.skills or [])
        allowed_tools = list(catalog.allowed_tools or [])
        scope = list(catalog.scope or [])
        agent = AgentInstance(
            company_id=company_id,
            catalog_agent_id=catalog.id,
            subscription_id=subscription.id,
            name=catalog.name or "Reservation Desk",
            template_version=catalog.version,
            instructions=catalog.default_instructions or "",
            skills=skills,
            allowed_tools=allowed_tools,
            scope=scope,
            autonomy=catalog.default_autonomy or "1",
            policies=dict(catalog.default_policies or {}),
            configuration={
                "role": catalog.role,
                "skills": skills,
                "allowed_tools": allowed_tools,
            },
            supervisor_user_id=user_id,
            status="active",
        )
        db.add(agent)
        db.flush()
        hired_now = True

    instruction = (
        "Search availability for Alila Hotel for 2 guests. "
        "Check-in 2026-10-30, check-out 2026-10-31. "
        "Use search_availability. Summarize matching rooms and rates. "
        "Do not book unless asked."
    )
    task = Task(
        company_id=company_id,
        agent_instance_id=agent.id,
        title="Demo: Alila availability 30–31 Oct 2026",
        instruction=instruction,
        mode="execute",
        status=TaskStatus.PENDING.value,
    )
    db.add(task)
    db.flush()
    return {
        **seed,
        "task_id": task.id,
        "agent_instance_id": agent.id,
        "agent_name": agent.name,
        "agent_hired": hired_now,
        "instruction": instruction,
        "next_step": "Open Tasks → Run execute (or Chat → Run task now).",
    }
