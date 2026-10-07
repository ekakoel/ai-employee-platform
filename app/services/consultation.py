"""Job 07 — Consultation mode: recommend without side-effect tools."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.agents.context import load_agent_context
from app.knowledge.retrieval import search_knowledge_chunks
from app.models.entities import Task, TaskStatus
from app.services.audit import record_audit
from app.services.experience import search_validated_experiences


# Tools that are safe during consultation (read-only).
READ_ONLY_TOOL_PREFIXES = ("search_", "get_", "list_", "read_", "find_")
READ_ONLY_TOOL_NAMES = frozenset(
    {
        "search_contract",
        "search_availability",
        "get_reservation",
        "read_document",
        "search_knowledge",
    }
)


def is_read_only_tool(tool_name: str) -> bool:
    name = (tool_name or "").strip().lower()
    if name in READ_ONLY_TOOL_NAMES:
        return True
    return name.startswith(READ_ONLY_TOOL_PREFIXES)


def build_consultation_result(
    db: Session,
    *,
    task: Task,
) -> dict[str, Any]:
    """
    Produce a structured recommendation using context/knowledge/experience.

    Guarantees: side_effects_executed is always False.
    """
    from app.models.entities import AgentInstance

    agent = db.get(AgentInstance, task.agent_instance_id)
    if agent is None:
        raise ValueError("Agent instance not found.")
    context = load_agent_context(db, agent, task)

    knowledge = list(context.retrieved_knowledge or [])
    experiences = list(context.experiences or [])
    # Extra search if context did not load
    if not knowledge and task.instruction:
        knowledge = search_knowledge_chunks(
            db,
            company_id=task.company_id,
            agent_instance_id=task.agent_instance_id,
            query=f"{task.title} {task.instruction}",
            limit=5,
        )
    if not experiences and task.instruction:
        experiences = search_validated_experiences(
            db,
            company_id=task.company_id,
            agent_instance_id=task.agent_instance_id,
            query=f"{task.title} {task.instruction}",
            limit=3,
        )

    rationale_parts = []
    if knowledge:
        rationale_parts.append(
            f"Found {len(knowledge)} relevant knowledge chunk(s)."
        )
        for k in knowledge[:2]:
            snippet = (k.get("content") or "")[:200]
            if snippet:
                rationale_parts.append(f"- Knowledge: {snippet}")
    if experiences:
        rationale_parts.append(
            f"Found {len(experiences)} validated experience(s)."
        )
        for e in experiences[:2]:
            lesson = e.get("lesson") or e.get("decision") or ""
            if lesson:
                rationale_parts.append(f"- Experience: {lesson[:200]}")
    if context.memories:
        rationale_parts.append(
            f"Agent has {len(context.memories)} active memor(ies)."
        )

    if not rationale_parts:
        rationale_parts.append(
            "Limited company knowledge matched this question; "
            "recommendation is conservative."
        )

    # Deterministic recommendation template (LLM optional later)
    recommendation = (
        f"Regarding '{task.title}': based on available company knowledge "
        f"and agent scope ({context.agent_role or 'agent'}), "
        f"prefer a cautious approach aligned with existing policies. "
        f"Do not take irreversible action until a human confirms "
        f"an execute-mode task."
    )

    alternatives = [
        "Proceed with an execute-mode task after human approval.",
        "Gather more information with read-only search tools only.",
        "Escalate to the AI supervisor / manager for a decision.",
    ]

    confidence = 0.55
    if knowledge:
        confidence += 0.15
    if experiences:
        confidence += 0.15
    confidence = min(confidence, 0.9)

    return {
        "mode": "consult",
        "recommendation": recommendation,
        "rationale": "\n".join(rationale_parts),
        "expected_impact": (
            "No external systems were changed. "
            "This is advisory only."
        ),
        "alternatives": alternatives,
        "confidence": confidence,
        "side_effects_executed": False,
        "retrieved_knowledge_count": len(knowledge),
        "experience_count": len(experiences),
        "notes": (
            "Consultation mode: no side-effect tools were executed. "
            "Create a task with mode=execute to perform actions."
        ),
    }


def run_consultation(
    db: Session,
    *,
    company_id: str,
    task_id: str,
) -> Task:
    task = db.get(Task, task_id)
    if task is None or task.company_id != company_id:
        raise ValueError("Task not found for this company.")
    if task.mode != "consult":
        raise ValueError("Task is not in consult mode.")
    if task.status not in (
        TaskStatus.PENDING.value,
        TaskStatus.PLANNING.value,
    ):
        raise ValueError(
            f"Task cannot be consulted from status '{task.status}'."
        )

    task.status = TaskStatus.RUNNING.value
    db.flush()

    result = build_consultation_result(db, task=task)
    task.result = json.dumps(result, ensure_ascii=False)
    task.status = TaskStatus.COMPLETED.value

    record_audit(
        db,
        company_id=company_id,
        agent_instance_id=task.agent_instance_id,
        task_id=task.id,
        action="task.consult",
        resource_type="task",
        resource_id=task.id,
        status="success",
        details={
            "side_effects_executed": False,
            "confidence": result["confidence"],
        },
    )
    db.commit()
    db.refresh(task)
    return task
