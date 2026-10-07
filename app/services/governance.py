"""Job 14 / Phase 11 — Performance & governance metrics (read-only analytics)."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    AgentInstance,
    Approval,
    AuditLog,
    AutomationRun,
    DelegationRequest,
    Experience,
    Task,
)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _count_by(items: list, key_fn) -> dict[str, int]:
    c: Counter[str] = Counter()
    for item in items:
        k = key_fn(item)
        c[str(k if k is not None else "unknown")] += 1
    return dict(c)


def company_overview(db: Session, *, company_id: str) -> dict[str, Any]:
    agents = list(
        db.scalars(
            select(AgentInstance).where(AgentInstance.company_id == company_id)
        ).all()
    )
    tasks = list(
        db.scalars(select(Task).where(Task.company_id == company_id)).all()
    )
    approvals = list(
        db.scalars(select(Approval).where(Approval.company_id == company_id)).all()
    )
    experiences = list(
        db.scalars(
            select(Experience).where(Experience.company_id == company_id)
        ).all()
    )
    audits = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.company_id == company_id)
            .order_by(AuditLog.created_at.desc())
            .limit(500)
        ).all()
    )
    automations = list(
        db.scalars(
            select(AutomationRun).where(AutomationRun.company_id == company_id)
        ).all()
    )
    delegations = list(
        db.scalars(
            select(DelegationRequest).where(
                DelegationRequest.company_id == company_id
            )
        ).all()
    )

    pending_approvals = [a for a in approvals if a.status == "pending"]
    completed_tasks = [t for t in tasks if t.status == "completed"]
    validated_exp = [
        e for e in experiences if e.validation_status == "validated"
    ]

    avg_confidence = (
        sum(float(e.confidence or 0) for e in validated_exp) / len(validated_exp)
        if validated_exp
        else 0.0
    )

    return {
        "company_id": company_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workforce": {
            "agents_total": len(agents),
            "agents_active": sum(1 for a in agents if a.status == "active"),
            "agents_by_status": _count_by(agents, lambda a: a.status),
        },
        "tasks": {
            "total": len(tasks),
            "by_status": _count_by(tasks, lambda t: t.status),
            "by_mode": _count_by(tasks, lambda t: getattr(t, "mode", "execute") or "execute"),
            "completed": len(completed_tasks),
            "open": sum(1 for t in tasks if t.status not in ("completed", "cancelled")),
        },
        "approvals": {
            "total": len(approvals),
            "pending": len(pending_approvals),
            "by_status": _count_by(approvals, lambda a: a.status),
        },
        "experiences": {
            "total": len(experiences),
            "by_status": _count_by(experiences, lambda e: e.validation_status),
            "validated": len(validated_exp),
            "avg_confidence_validated": round(avg_confidence, 4),
            "total_success_count": sum(int(e.success_count or 0) for e in experiences),
        },
        "automation": {
            "runs_total": len(automations),
            "by_status": _count_by(automations, lambda r: r.status),
        },
        "delegation": {
            "total": len(delegations),
            "by_status": _count_by(delegations, lambda d: d.status),
        },
        "audit": {
            "recent_count": len(audits),
            "by_action": _count_by(audits, lambda a: a.action),
            "by_status": _count_by(audits, lambda a: a.status),
        },
    }


def agent_performance(db: Session, *, company_id: str) -> list[dict[str, Any]]:
    agents = list(
        db.scalars(
            select(AgentInstance).where(AgentInstance.company_id == company_id)
        ).all()
    )
    tasks = list(
        db.scalars(select(Task).where(Task.company_id == company_id)).all()
    )
    experiences = list(
        db.scalars(
            select(Experience).where(Experience.company_id == company_id)
        ).all()
    )
    approvals = list(
        db.scalars(select(Approval).where(Approval.company_id == company_id)).all()
    )

    tasks_by_agent: dict[str, list] = defaultdict(list)
    for t in tasks:
        tasks_by_agent[t.agent_instance_id].append(t)
    exp_by_agent: dict[str, list] = defaultdict(list)
    for e in experiences:
        if e.agent_instance_id:
            exp_by_agent[e.agent_instance_id].append(e)
    appr_by_agent: dict[str, list] = defaultdict(list)
    for a in approvals:
        if a.agent_instance_id:
            appr_by_agent[a.agent_instance_id].append(a)

    rows = []
    for agent in agents:
        at = tasks_by_agent.get(agent.id, [])
        ae = exp_by_agent.get(agent.id, [])
        aa = appr_by_agent.get(agent.id, [])
        completed = sum(1 for t in at if t.status == "completed")
        failed = sum(1 for t in at if t.status == "failed")
        validated = [e for e in ae if e.validation_status == "validated"]
        avg_conf = (
            sum(float(e.confidence or 0) for e in validated) / len(validated)
            if validated
            else 0.0
        )
        rows.append(
            {
                "agent_instance_id": agent.id,
                "name": agent.name,
                "status": agent.status,
                "tasks_total": len(at),
                "tasks_completed": completed,
                "tasks_failed": failed,
                "completion_rate": round(completed / len(at), 4) if at else 0.0,
                "approvals_total": len(aa),
                "approvals_pending": sum(1 for x in aa if x.status == "pending"),
                "experiences_total": len(ae),
                "experiences_validated": len(validated),
                "avg_experience_confidence": round(avg_conf, 4),
                "experience_success_count": sum(
                    int(e.success_count or 0) for e in ae
                ),
            }
        )
    rows.sort(key=lambda r: r["tasks_total"], reverse=True)
    return rows


def approval_metrics(db: Session, *, company_id: str) -> dict[str, Any]:
    approvals = list(
        db.scalars(select(Approval).where(Approval.company_id == company_id)).all()
    )
    latencies_hours: list[float] = []
    for a in approvals:
        created = _aware(getattr(a, "created_at", None))
        decided = _aware(getattr(a, "reviewed_at", None))
        if created and decided and a.status in ("approved", "rejected"):
            delta = (decided - created).total_seconds() / 3600.0
            if delta >= 0:
                latencies_hours.append(delta)

    avg_latency = (
        sum(latencies_hours) / len(latencies_hours) if latencies_hours else None
    )
    return {
        "total": len(approvals),
        "by_status": _count_by(approvals, lambda a: a.status),
        "pending": sum(1 for a in approvals if a.status == "pending"),
        "decided_with_latency_samples": len(latencies_hours),
        "avg_decision_latency_hours": round(avg_latency, 4)
        if avg_latency is not None
        else None,
        "max_decision_latency_hours": round(max(latencies_hours), 4)
        if latencies_hours
        else None,
    }


def experience_quality(db: Session, *, company_id: str) -> dict[str, Any]:
    experiences = list(
        db.scalars(
            select(Experience).where(Experience.company_id == company_id)
        ).all()
    )
    validated = [e for e in experiences if e.validation_status == "validated"]
    rejected = [e for e in experiences if e.validation_status == "rejected"]
    with_correction = [
        e for e in experiences if (e.human_correction or "").strip()
    ]
    return {
        "total": len(experiences),
        "by_status": _count_by(experiences, lambda e: e.validation_status),
        "validated": len(validated),
        "rejected": len(rejected),
        "with_human_correction": len(with_correction),
        "avg_confidence_all": round(
            sum(float(e.confidence or 0) for e in experiences) / len(experiences),
            4,
        )
        if experiences
        else 0.0,
        "avg_confidence_validated": round(
            sum(float(e.confidence or 0) for e in validated) / len(validated),
            4,
        )
        if validated
        else 0.0,
        "total_reuse_success_count": sum(
            int(e.success_count or 0) for e in experiences
        ),
        "top_lessons": [
            {
                "id": e.id,
                "lesson": (e.lesson or "")[:200],
                "confidence": e.confidence,
                "success_count": e.success_count,
            }
            for e in sorted(
                validated,
                key=lambda x: (int(x.success_count or 0), float(x.confidence or 0)),
                reverse=True,
            )[:10]
        ],
    }


def audit_analytics(
    db: Session,
    *,
    company_id: str,
    limit: int = 100,
) -> dict[str, Any]:
    rows = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.company_id == company_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        ).all()
    )
    return {
        "sample_size": len(rows),
        "by_action": _count_by(rows, lambda a: a.action),
        "by_status": _count_by(rows, lambda a: a.status),
        "by_resource_type": _count_by(rows, lambda a: a.resource_type),
        "recent": [
            {
                "id": a.id,
                "action": a.action,
                "resource_type": a.resource_type,
                "resource_id": a.resource_id,
                "status": a.status,
                "agent_instance_id": a.agent_instance_id,
                "created_at": a.created_at.isoformat()
                if a.created_at
                else None,
            }
            for a in rows[:25]
        ],
    }
