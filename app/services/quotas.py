"""Job 22 — Plans, quotas, and usage metering."""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import (
    AgentInstance,
    AgentStatus,
    AutomationRule,
    CompanyPlanSubscription,
    Plan,
    Task,
    UsageCounter,
)

METRIC_TASKS = "tasks"
METRIC_LLM = "llm_calls"


def _today() -> str:
    return date.today().isoformat()


def seed_default_plans(db: Session) -> None:
    """Ensure free / pro plans exist."""
    defaults = [
        {
            "code": "free",
            "name": "Free",
            "description": "Starter quotas for evaluation",
            "max_agents": 3,
            "max_tasks_day": 50,
            "max_automations": 5,
            "max_llm_calls_day": 200,
        },
        {
            "code": "pro",
            "name": "Pro",
            "description": "Higher limits for production teams",
            "max_agents": 25,
            "max_tasks_day": 1000,
            "max_automations": 100,
            "max_llm_calls_day": 10000,
        },
        {
            "code": "enterprise",
            "name": "Enterprise",
            "description": "Large org limits",
            "max_agents": 500,
            "max_tasks_day": 50000,
            "max_automations": 2000,
            "max_llm_calls_day": 500000,
        },
    ]
    for d in defaults:
        existing = db.scalar(select(Plan).where(Plan.code == d["code"]))
        if existing:
            continue
        db.add(Plan(**d))
    db.flush()


def get_or_assign_plan(db: Session, company_id: str) -> tuple[Plan, CompanyPlanSubscription]:
    """Return company's plan; assign free plan if missing."""
    seed_default_plans(db)
    sub = db.scalar(
        select(CompanyPlanSubscription).where(
            CompanyPlanSubscription.company_id == company_id,
            CompanyPlanSubscription.status == "active",
        )
    )
    if sub:
        plan = db.get(Plan, sub.plan_id)
        if plan:
            return plan, sub
    free = db.scalar(select(Plan).where(Plan.code == "free"))
    if not free:
        raise RuntimeError("Free plan missing after seed")
    sub = CompanyPlanSubscription(
        company_id=company_id,
        plan_id=free.id,
        status="active",
    )
    db.add(sub)
    db.flush()
    return free, sub


def set_company_plan(db: Session, company_id: str, plan_code: str) -> CompanyPlanSubscription:
    seed_default_plans(db)
    plan = db.scalar(select(Plan).where(Plan.code == plan_code, Plan.is_active.is_(True)))
    if not plan:
        raise ValueError(f"Plan '{plan_code}' not found")
    sub = db.scalar(
        select(CompanyPlanSubscription).where(
            CompanyPlanSubscription.company_id == company_id
        )
    )
    if sub:
        sub.plan_id = plan.id
        sub.status = "active"
        sub.started_at = datetime.now(timezone.utc)
    else:
        sub = CompanyPlanSubscription(
            company_id=company_id,
            plan_id=plan.id,
            status="active",
        )
        db.add(sub)
    db.flush()
    return sub


def get_usage(db: Session, company_id: str, metric: str, period: str | None = None) -> int:
    period = period or _today()
    row = db.scalar(
        select(UsageCounter).where(
            UsageCounter.company_id == company_id,
            UsageCounter.metric == metric,
            UsageCounter.period_date == period,
        )
    )
    return int(row.count) if row else 0


def increment_usage(
    db: Session,
    company_id: str,
    metric: str,
    by: int = 1,
) -> int:
    period = _today()
    row = db.scalar(
        select(UsageCounter).where(
            UsageCounter.company_id == company_id,
            UsageCounter.metric == metric,
            UsageCounter.period_date == period,
        )
    )
    if row:
        row.count = int(row.count) + by
        db.flush()
        return int(row.count)
    row = UsageCounter(
        company_id=company_id,
        metric=metric,
        period_date=period,
        count=by,
    )
    db.add(row)
    db.flush()
    return by


def count_active_agents(db: Session, company_id: str) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(AgentInstance)
            .where(
                AgentInstance.company_id == company_id,
                AgentInstance.status == AgentStatus.ACTIVE.value,
            )
        )
        or 0
    )


def count_automations(db: Session, company_id: str) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(AutomationRule)
            .where(AutomationRule.company_id == company_id)
        )
        or 0
    )


def enforce_agent_quota(db: Session, company_id: str) -> None:
    plan, _ = get_or_assign_plan(db, company_id)
    used = count_active_agents(db, company_id)
    if used >= plan.max_agents:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "quota_exceeded",
                "metric": "max_agents",
                "limit": plan.max_agents,
                "used": used,
                "plan": plan.code,
            },
        )


def enforce_task_quota(db: Session, company_id: str) -> None:
    plan, _ = get_or_assign_plan(db, company_id)
    used = get_usage(db, company_id, METRIC_TASKS)
    if used >= plan.max_tasks_day:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "quota_exceeded",
                "metric": "max_tasks_day",
                "limit": plan.max_tasks_day,
                "used": used,
                "plan": plan.code,
            },
        )


def enforce_automation_quota(db: Session, company_id: str) -> None:
    plan, _ = get_or_assign_plan(db, company_id)
    used = count_automations(db, company_id)
    if used >= plan.max_automations:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "quota_exceeded",
                "metric": "max_automations",
                "limit": plan.max_automations,
                "used": used,
                "plan": plan.code,
            },
        )


def record_task_created(db: Session, company_id: str) -> None:
    increment_usage(db, company_id, METRIC_TASKS)


def record_llm_call(db: Session, company_id: str) -> None:
    """Stub counter for future LLM metering."""
    increment_usage(db, company_id, METRIC_LLM)


def usage_summary(db: Session, company_id: str) -> dict:
    plan, sub = get_or_assign_plan(db, company_id)
    return {
        "plan": {
            "code": plan.code,
            "name": plan.name,
            "max_agents": plan.max_agents,
            "max_tasks_day": plan.max_tasks_day,
            "max_automations": plan.max_automations,
            "max_llm_calls_day": plan.max_llm_calls_day,
        },
        "subscription_id": sub.id,
        "usage": {
            "agents": count_active_agents(db, company_id),
            "tasks_today": get_usage(db, company_id, METRIC_TASKS),
            "automations": count_automations(db, company_id),
            "llm_calls_today": get_usage(db, company_id, METRIC_LLM),
        },
        "period_date": _today(),
    }
