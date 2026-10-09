"""Job 27 — Multi-step automation workflows (simple ordered DAG / state machine)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    AgentInstance,
    AgentStatus,
    Approval,
    ApprovalStatus,
    DelegationRequest,
    Task,
    TaskStatus,
    WorkflowDefinition,
    WorkflowRun,
    WorkflowRunStatus,
)
from app.services.audit import record_audit
from app.services.consultation import run_consultation
from app.services.notifications import notify_users
from app.models.entities import NotificationType

ALLOWED_STEP_TYPES = {
    "create_task",
    "wait_approval",
    "delegate",
    "emit_event",
    "complete",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def validate_steps(steps: list[dict[str, Any]]) -> None:
    if not steps or not isinstance(steps, list):
        raise ValueError("steps must be a non-empty list")
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError(f"step {i} must be an object")
        st = step.get("type")
        if st not in ALLOWED_STEP_TYPES:
            raise ValueError(
                f"step {i}: type must be one of {sorted(ALLOWED_STEP_TYPES)}"
            )


def create_definition(
    db: Session,
    *,
    company_id: str,
    name: str,
    steps: list[dict[str, Any]],
    description: str = "",
) -> WorkflowDefinition:
    validate_steps(steps)
    wf = WorkflowDefinition(
        company_id=company_id,
        name=name[:200],
        description=description or "",
        steps=list(steps),
        is_active=True,
    )
    db.add(wf)
    db.flush()
    return wf


def start_run(
    db: Session,
    *,
    definition: WorkflowDefinition,
    context: dict[str, Any] | None = None,
    user_id: str | None = None,
) -> WorkflowRun:
    if not definition.is_active:
        raise ValueError("Workflow definition is inactive")
    run = WorkflowRun(
        company_id=definition.company_id,
        definition_id=definition.id,
        status=WorkflowRunStatus.PENDING.value,
        current_step=0,
        context=dict(context or {}),
        step_results=[],
        started_at=_now(),
    )
    db.add(run)
    db.flush()
    record_audit(
        db,
        company_id=definition.company_id,
        user_id=user_id,
        action="workflow.run.start",
        resource_type="workflow_run",
        resource_id=run.id,
        status="success",
        details={"definition_id": definition.id},
    )
    return advance_run(db, run=run, definition=definition, user_id=user_id)


def _append_result(run: WorkflowRun, step_index: int, result: dict[str, Any]) -> None:
    results = list(run.step_results or [])
    results.append({"step": step_index, **result})
    run.step_results = results


def _fail(run: WorkflowRun, message: str) -> WorkflowRun:
    run.status = WorkflowRunStatus.FAILED.value
    run.error_message = message
    run.completed_at = _now()
    return run


def advance_run(
    db: Session,
    *,
    run: WorkflowRun,
    definition: WorkflowDefinition | None = None,
    user_id: str | None = None,
) -> WorkflowRun:
    """
    Execute steps from current_step until pause, complete, or fail.
    """
    if run.status in (
        WorkflowRunStatus.COMPLETED.value,
        WorkflowRunStatus.FAILED.value,
        WorkflowRunStatus.CANCELLED.value,
    ):
        return run

    definition = definition or db.get(WorkflowDefinition, run.definition_id)
    if not definition:
        return _fail(run, "Workflow definition not found")

    steps = list(definition.steps or [])
    run.status = WorkflowRunStatus.RUNNING.value
    db.flush()

    # Max iterations to avoid infinite loops
    guard = 0
    while run.current_step < len(steps) and guard < 50:
        guard += 1
        idx = run.current_step
        step = steps[idx]
        stype = step.get("type")

        try:
            if stype == "create_task":
                outcome = _step_create_task(db, run=run, step=step, user_id=user_id)
            elif stype == "wait_approval":
                outcome = _step_wait_approval(db, run=run, step=step)
            elif stype == "delegate":
                outcome = _step_delegate(db, run=run, step=step, user_id=user_id)
            elif stype == "emit_event":
                outcome = _step_emit_event(db, run=run, step=step)
            elif stype == "complete":
                outcome = {"status": "ok", "action": "complete"}
            else:
                return _fail(run, f"Unknown step type: {stype}")
        except Exception as exc:
            _append_result(run, idx, {"status": "error", "error": str(exc)})
            return _fail(run, str(exc))

        _append_result(run, idx, outcome)

        if outcome.get("pause"):
            run.status = WorkflowRunStatus.PAUSED_APPROVAL.value
            db.flush()
            return run

        if outcome.get("fail"):
            return _fail(run, outcome.get("error") or "Step failed")

        run.current_step = idx + 1
        db.flush()

        if stype == "complete":
            break

    run.status = WorkflowRunStatus.COMPLETED.value
    run.completed_at = _now()
    db.flush()
    record_audit(
        db,
        company_id=run.company_id,
        user_id=user_id,
        action="workflow.run.completed",
        resource_type="workflow_run",
        resource_id=run.id,
        status="success",
    )
    return run


def resume_run(
    db: Session,
    *,
    run: WorkflowRun,
    user_id: str | None = None,
) -> WorkflowRun:
    """Resume a paused workflow (e.g. after approval)."""
    if run.status not in (
        WorkflowRunStatus.PAUSED_APPROVAL.value,
        WorkflowRunStatus.PENDING.value,
        WorkflowRunStatus.RUNNING.value,
    ):
        raise ValueError(f"Cannot resume run in status={run.status}")
    # Move past wait_approval if approval satisfied
    definition = db.get(WorkflowDefinition, run.definition_id)
    if not definition:
        return _fail(run, "Workflow definition not found")
    steps = list(definition.steps or [])
    if run.current_step < len(steps):
        step = steps[run.current_step]
        if step.get("type") == "wait_approval":
            outcome = _step_wait_approval(db, run=run, step=step)
            if outcome.get("pause"):
                run.status = WorkflowRunStatus.PAUSED_APPROVAL.value
                db.flush()
                return run
            _append_result(run, run.current_step, outcome)
            run.current_step += 1
            db.flush()
    return advance_run(db, run=run, definition=definition, user_id=user_id)


def _step_create_task(
    db: Session, *, run: WorkflowRun, step: dict[str, Any], user_id: str | None = None
) -> dict[str, Any]:
    agent_id = step.get("agent_instance_id") or run.context.get("agent_instance_id")
    if not agent_id:
        return {"fail": True, "error": "create_task requires agent_instance_id"}
    agent = db.get(AgentInstance, agent_id)
    if not agent or agent.company_id != run.company_id:
        return {"fail": True, "error": "Agent not found"}
    if agent.status != AgentStatus.ACTIVE.value:
        return {"fail": True, "error": f"Agent not active ({agent.status})"}
    from app.services.access import require_execution_actor
    require_execution_actor(db, company_id=run.company_id, agent_instance_id=agent.id, user_id=user_id)

    title = str(step.get("title") or run.context.get("title") or "Workflow task")[:300]
    instruction = str(
        step.get("instruction") or run.context.get("instruction") or title
    )
    mode = step.get("mode") or "consult"
    if mode not in ("consult", "execute"):
        mode = "consult"

    task = Task(
        company_id=run.company_id,
        agent_instance_id=agent_id,
        title=title,
        instruction=instruction,
        mode=mode,
        status=TaskStatus.PENDING.value,
    )
    db.add(task)
    db.flush()

    ctx = dict(run.context or {})
    ctx["last_task_id"] = task.id
    run.context = ctx

    # Auto-run consult when requested
    if mode == "consult" and step.get("auto_run", True):
        try:
            run_consultation(db, company_id=run.company_id, task_id=task.id, user_id=user_id)
            db.refresh(task)
        except Exception as exc:
            return {
                "status": "task_created",
                "task_id": task.id,
                "consult_error": str(exc),
                "fail": True,
                "error": "Workflow consultation failed.",
            }
        if task.status in (TaskStatus.FAILED.value, TaskStatus.CANCELLED.value):
            return {"fail": True, "error": task.result or "Workflow child task failed.", "task_id": task.id}

    if task.status == TaskStatus.WAITING_APPROVAL.value:
        return {
            "status": "paused",
            "pause": True,
            "task_id": task.id,
            "reason": "waiting_approval",
        }

    return {
        "status": "ok",
        "task_id": task.id,
        "task_status": task.status,
    }


def _step_wait_approval(
    db: Session, *, run: WorkflowRun, step: dict[str, Any]
) -> dict[str, Any]:
    task_id = step.get("task_id") or run.context.get("last_task_id")
    approval_id = step.get("approval_id") or run.context.get("last_approval_id")

    if approval_id:
        approval = db.get(Approval, approval_id)
        if not approval or approval.company_id != run.company_id:
            return {"fail": True, "error": "Approval not found"}
        if approval.status == ApprovalStatus.PENDING.value:
            return {"status": "waiting", "pause": True, "approval_id": approval_id}
        if approval.status == ApprovalStatus.REJECTED.value:
            return {
                "fail": True,
                "error": "Approval rejected",
                "approval_id": approval_id,
            }
        return {"status": "ok", "approval_id": approval_id, "approval_status": approval.status}

    if task_id:
        task = db.get(Task, task_id)
        if not task or task.company_id != run.company_id:
            return {"fail": True, "error": "Task not found for wait_approval"}
        if task.status == TaskStatus.WAITING_APPROVAL.value:
            return {"status": "waiting", "pause": True, "task_id": task_id}
        if task.status == TaskStatus.FAILED.value:
            return {"fail": True, "error": "Linked task failed", "task_id": task_id}
        # also check pending approvals for this task
        pending = db.scalar(
            select(Approval).where(
                Approval.company_id == run.company_id,
                Approval.task_id == task_id,
                Approval.status == ApprovalStatus.PENDING.value,
            )
        )
        if pending:
            ctx = dict(run.context or {})
            ctx["last_approval_id"] = pending.id
            run.context = ctx
            return {
                "status": "waiting",
                "pause": True,
                "approval_id": pending.id,
                "task_id": task_id,
            }
        return {"status": "ok", "task_id": task_id, "task_status": task.status}

    return {"fail": True, "error": "wait_approval needs task_id or approval_id"}


def _step_delegate(
    db: Session,
    *,
    run: WorkflowRun,
    step: dict[str, Any],
    user_id: str | None,
) -> dict[str, Any]:
    source = step.get("source_agent_instance_id") or run.context.get("agent_instance_id")
    target = step.get("target_agent_instance_id")
    if not source or not target:
        return {
            "fail": True,
            "error": "delegate requires source_agent_instance_id and target_agent_instance_id",
        }
    from app.services.access import require_execution_actor
    for employee_id in (source, target):
        employee = db.get(AgentInstance, employee_id)
        if not employee or employee.company_id != run.company_id or employee.status != AgentStatus.ACTIVE.value:
            return {"fail": True, "error": "Delegation employee not active in this company."}
        require_execution_actor(db, company_id=run.company_id, agent_instance_id=employee_id, user_id=user_id)
    title = str(step.get("title") or "Workflow delegation")[:300]
    instruction = str(step.get("instruction") or title)
    capability = str(step.get("capability") or "general")
    req = DelegationRequest(
        company_id=run.company_id,
        source_agent_instance_id=source,
        target_agent_instance_id=target,
        requested_by_user_id=user_id,
        capability=capability,
        title=title,
        instruction=instruction,
        status="pending",
        validation_notes="workflow step",
        timeout_seconds=int(step.get("timeout_seconds") or 300),
    )
    db.add(req)
    db.flush()
    ctx = dict(run.context or {})
    ctx["last_delegation_id"] = req.id
    run.context = ctx
    return {"status": "ok", "delegation_request_id": req.id}


def _step_emit_event(
    db: Session, *, run: WorkflowRun, step: dict[str, Any]
) -> dict[str, Any]:
    event_type = str(step.get("event_type") or "workflow.event")
    payload = dict(step.get("payload") or {})
    payload["workflow_run_id"] = run.id
    # Optional: notify supervisor from context
    supervisor_id = run.context.get("notify_user_id")
    if supervisor_id:
        try:
            notify_users(
                db,
                company_id=run.company_id,
                user_ids=[supervisor_id],
                type=NotificationType.SYSTEM.value,
                title=f"Workflow event: {event_type}",
                body=str(payload)[:500],
                payload=payload,
            )
        except Exception:
            pass
    record_audit(
        db,
        company_id=run.company_id,
        action="workflow.event",
        resource_type="workflow_run",
        resource_id=run.id,
        status="success",
        details={"event_type": event_type, "payload": payload},
    )
    return {"status": "ok", "event_type": event_type}
