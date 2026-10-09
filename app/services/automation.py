"""Job 11 — Automation: schedule, events, retries, idempotency, approval pause."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import (
    AgentInstance,
    AgentStatus,
    AutomationRule,
    AutomationRun,
    AutomationRunStatus,
    AutomationTriggerType,
    Task,
    TaskStatus,
)
from app.services.audit import record_audit
from app.services.consultation import run_consultation


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def render_template(template: str, payload: dict[str, Any]) -> str:
    text = template or ""
    for key, value in (payload or {}).items():
        text = text.replace("{" + str(key) + "}", str(value))
    return text


def get_existing_run(
    db: Session,
    *,
    company_id: str,
    idempotency_key: str,
) -> AutomationRun | None:
    return db.scalar(
        select(AutomationRun).where(
            AutomationRun.company_id == company_id,
            AutomationRun.idempotency_key == idempotency_key,
        )
    )


def execute_run(
    db: Session,
    *,
    rule: AutomationRule,
    run: AutomationRun,
    user_id: str | None = None,
) -> AutomationRun:
    """
    Create target task and optionally complete consult mode.

    Idempotent: if run already completed/paused with task_id, return as-is.
    """
    if run.status in (
        AutomationRunStatus.COMPLETED.value,
        AutomationRunStatus.PAUSED_APPROVAL.value,
    ) and run.task_id:
        return run

    agent = db.get(AgentInstance, rule.agent_instance_id)
    if agent is None or agent.company_id != rule.company_id:
        run.status = AutomationRunStatus.FAILED.value
        run.error_message = "Agent not found for automation rule."
        run.completed_at = _now()
        db.flush()
        return run

    if agent.status != AgentStatus.ACTIVE.value:
        run.status = AutomationRunStatus.FAILED.value
        run.error_message = f"Agent is not active (status={agent.status})."
        run.completed_at = _now()
        db.flush()
        return run
    from app.services.access import require_execution_actor
    try:
        require_execution_actor(db, company_id=rule.company_id, agent_instance_id=agent.id, user_id=user_id)
    except Exception as exc:
        run.status = AutomationRunStatus.FAILED.value
        run.error_message = str(exc)
        run.completed_at = _now()
        db.flush()
        return run

    run.status = AutomationRunStatus.RUNNING.value
    run.started_at = _now()
    db.flush()

    title = render_template(rule.task_title_template, run.trigger_payload or {})
    instruction = render_template(
        rule.task_instruction_template, run.trigger_payload or {}
    )

    task = Task(
        company_id=rule.company_id,
        agent_instance_id=rule.agent_instance_id,
        title=title[:300],
        instruction=instruction,
        mode=rule.task_mode if rule.task_mode in ("execute", "consult") else "consult",
        status=TaskStatus.PENDING.value,
    )
    db.add(task)
    db.flush()
    run.task_id = task.id

    record_audit(
        db,
        company_id=rule.company_id,
        user_id=user_id,
        agent_instance_id=rule.agent_instance_id,
        task_id=task.id,
        action="automation.run",
        resource_type="automation_run",
        resource_id=run.id,
        status="success",
        details={
            "rule_id": rule.id,
            "idempotency_key": run.idempotency_key,
            "attempt": run.attempt,
            "mode": task.mode,
        },
    )

    try:
        if task.mode == "consult":
            task = run_consultation(
                db, company_id=rule.company_id, task_id=task.id, user_id=user_id
            )
            db.refresh(run)
            db.refresh(task)
            if task.status == TaskStatus.WAITING_APPROVAL.value:
                run.status = AutomationRunStatus.PAUSED_APPROVAL.value
            elif task.status == TaskStatus.COMPLETED.value:
                run.status = AutomationRunStatus.COMPLETED.value
                run.completed_at = _now()
            elif task.status in (TaskStatus.FAILED.value, TaskStatus.CANCELLED.value):
                run.status = AutomationRunStatus.FAILED.value
                run.error_message = "Child task failed."
                run.completed_at = _now()
            else:
                run.status = AutomationRunStatus.COMPLETED.value
                run.completed_at = _now()
        else:
            # execute mode: task left pending; automation run completes handoff
            run.status = AutomationRunStatus.COMPLETED.value
            run.completed_at = _now()

        rule.last_run_at = _now()
        if (
            rule.trigger_type == AutomationTriggerType.SCHEDULE.value
            and rule.interval_seconds
        ):
            base = _aware(rule.next_run_at) or _now()
            # advance next_run_at from now to avoid stampede
            rule.next_run_at = _now() + timedelta(seconds=int(rule.interval_seconds))

        db.commit()
        db.refresh(run)
        return run

    except Exception as exc:
        run.status = AutomationRunStatus.FAILED.value
        run.error_message = str(exc)
        run.completed_at = _now()
        record_audit(
            db,
            company_id=rule.company_id,
            user_id=user_id,
            agent_instance_id=rule.agent_instance_id,
            task_id=run.task_id,
            action="automation.failed",
            resource_type="automation_run",
            resource_id=run.id,
            status="failure",
            details={"error": str(exc)},
        )
        db.commit()
        db.refresh(run)
        return run


def create_and_execute_run(
    db: Session,
    *,
    rule: AutomationRule,
    idempotency_key: str,
    payload: dict[str, Any] | None = None,
    user_id: str | None = None,
) -> AutomationRun:
    existing = get_existing_run(
        db, company_id=rule.company_id, idempotency_key=idempotency_key
    )
    if existing:
        # Idempotent return — do not create a second task
        return existing

    run = AutomationRun(
        company_id=rule.company_id,
        rule_id=rule.id,
        idempotency_key=idempotency_key,
        attempt=1,
        status=AutomationRunStatus.PENDING.value,
        trigger_payload=dict(payload or {}),
    )
    db.add(run)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = get_existing_run(
            db, company_id=rule.company_id, idempotency_key=idempotency_key
        )
        if existing:
            return existing
        raise

    return execute_run(db, rule=rule, run=run, user_id=user_id)


def tick_schedules(
    db: Session,
    *,
    company_id: str,
    user_id: str | None = None,
    limit: int = 50,
) -> list[AutomationRun]:
    """Fire due schedule rules for a company (worker-less MVP tick)."""
    now = _now()
    rules = list(
        db.scalars(
            select(AutomationRule).where(
                AutomationRule.company_id == company_id,
                AutomationRule.is_active.is_(True),
                AutomationRule.trigger_type == AutomationTriggerType.SCHEDULE.value,
            )
        ).all()
    )
    runs: list[AutomationRun] = []
    for rule in rules:
        if not rule.next_run_at:
            continue
        due = _aware(rule.next_run_at)
        if due is None or due > now:
            continue
        # idempotency per due window
        key = f"schedule:{rule.id}:{due.isoformat()}"
        run = create_and_execute_run(
            db,
            rule=rule,
            idempotency_key=key,
            payload={"trigger": "schedule", "due_at": due.isoformat()},
            user_id=user_id,
        )
        runs.append(run)
        if len(runs) >= limit:
            break
    return runs


def fire_event(
    db: Session,
    *,
    company_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    user_id: str | None = None,
) -> list[AutomationRun]:
    """Fire all active event rules matching event_type."""
    rules = list(
        db.scalars(
            select(AutomationRule).where(
                AutomationRule.company_id == company_id,
                AutomationRule.is_active.is_(True),
                AutomationRule.trigger_type == AutomationTriggerType.EVENT.value,
                AutomationRule.event_type == event_type,
            )
        ).all()
    )
    key_base = idempotency_key or f"event:{event_type}:{uuid4()}"
    runs: list[AutomationRun] = []
    for i, rule in enumerate(rules):
        key = key_base if len(rules) == 1 else f"{key_base}:{rule.id}"
        run = create_and_execute_run(
            db,
            rule=rule,
            idempotency_key=key,
            payload={"trigger": "event", "event_type": event_type, **(payload or {})},
            user_id=user_id,
        )
        runs.append(run)
    return runs


def retry_run(
    db: Session,
    *,
    run: AutomationRun,
    user_id: str | None = None,
) -> AutomationRun:
    """Safe retry: only failed runs, under max_retries, new attempt with new key suffix."""
    rule = db.get(AutomationRule, run.rule_id)
    if rule is None:
        raise ValueError("Automation rule not found.")
    if run.status != AutomationRunStatus.FAILED.value:
        raise ValueError(
            f"Only failed runs can be retried (status={run.status})."
        )
    if run.attempt >= int(rule.max_retries or 0):
        raise ValueError(
            f"Max retries reached ({rule.max_retries})."
        )

    new_key = f"{run.idempotency_key}:retry:{run.attempt + 1}"
    existing = get_existing_run(
        db, company_id=run.company_id, idempotency_key=new_key
    )
    if existing:
        return existing

    new_run = AutomationRun(
        company_id=run.company_id,
        rule_id=rule.id,
        idempotency_key=new_key,
        attempt=run.attempt + 1,
        status=AutomationRunStatus.PENDING.value,
        trigger_payload=dict(run.trigger_payload or {}),
    )
    db.add(new_run)
    db.flush()
    return execute_run(db, rule=rule, run=new_run, user_id=user_id)


def sync_approval_pause(
    db: Session,
    *,
    run: AutomationRun,
) -> AutomationRun:
    """If linked task is waiting_approval, mark run paused_approval."""
    if not run.task_id:
        return run
    task = db.get(Task, run.task_id)
    if task and task.status == TaskStatus.WAITING_APPROVAL.value:
        run.status = AutomationRunStatus.PAUSED_APPROVAL.value
        db.flush()
    elif task and task.status == TaskStatus.COMPLETED.value:
        run.status = AutomationRunStatus.COMPLETED.value
        run.completed_at = _now()
        db.flush()
    return run
