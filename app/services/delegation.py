"""Job 09 — Inter-agent delegation execution."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.entities import (
    DelegationRequest,
    DelegationStatus,
    Task,
    TaskStatus,
)
from app.services.audit import record_audit
from app.services.consultation import run_consultation
from app.services.directory import validate_delegation_target


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def is_timed_out(req: DelegationRequest, now: datetime | None = None) -> bool:
    now = now or _now()
    created = _as_aware(req.created_at) or now
    timeout = int(req.timeout_seconds or 300)
    return now > created + timedelta(seconds=timeout)


def mark_timeout_if_needed(db: Session, req: DelegationRequest) -> bool:
    """If pending/accepted past timeout, mark failed. Returns True if timed out."""
    if req.status not in (
        DelegationStatus.PENDING.value,
        DelegationStatus.ACCEPTED.value,
    ):
        return False
    if not is_timed_out(req):
        return False
    req.status = DelegationStatus.FAILED.value
    req.error_message = (
        f"Delegation timed out after {req.timeout_seconds} seconds."
    )
    req.completed_at = _now()
    record_audit(
        db,
        company_id=req.company_id,
        agent_instance_id=req.source_agent_instance_id,
        action="delegation.timeout",
        resource_type="delegation_request",
        resource_id=req.id,
        status="failure",
        details={"timeout_seconds": req.timeout_seconds},
    )
    db.flush()
    return True


def accept_delegation(
    db: Session,
    *,
    req: DelegationRequest,
    user_id: str | None,
) -> DelegationRequest:
    if mark_timeout_if_needed(db, req):
        raise ValueError(req.error_message or "Delegation timed out.")
    if req.status != DelegationStatus.PENDING.value:
        raise ValueError(
            f"Cannot accept delegation in status '{req.status}'."
        )
    req.status = DelegationStatus.ACCEPTED.value
    record_audit(
        db,
        company_id=req.company_id,
        user_id=user_id,
        agent_instance_id=req.target_agent_instance_id,
        action="delegation.accept",
        resource_type="delegation_request",
        resource_id=req.id,
        status="success",
    )
    db.flush()
    return req


def reject_delegation(
    db: Session,
    *,
    req: DelegationRequest,
    user_id: str | None,
    reason: str = "",
) -> DelegationRequest:
    if req.status not in (
        DelegationStatus.PENDING.value,
        DelegationStatus.ACCEPTED.value,
    ):
        raise ValueError(
            f"Cannot reject delegation in status '{req.status}'."
        )
    req.status = DelegationStatus.REJECTED.value
    req.error_message = reason or "Rejected by operator."
    req.completed_at = _now()
    record_audit(
        db,
        company_id=req.company_id,
        user_id=user_id,
        agent_instance_id=req.target_agent_instance_id,
        action="delegation.reject",
        resource_type="delegation_request",
        resource_id=req.id,
        status="success",
        details={"reason": reason},
    )
    db.flush()
    return req


def cancel_delegation(
    db: Session,
    *,
    req: DelegationRequest,
    user_id: str | None,
) -> DelegationRequest:
    if req.status not in (
        DelegationStatus.PENDING.value,
        DelegationStatus.ACCEPTED.value,
    ):
        raise ValueError(
            f"Cannot cancel delegation in status '{req.status}'."
        )
    req.status = DelegationStatus.CANCELLED.value
    req.completed_at = _now()
    record_audit(
        db,
        company_id=req.company_id,
        user_id=user_id,
        agent_instance_id=req.source_agent_instance_id,
        action="delegation.cancel",
        resource_type="delegation_request",
        resource_id=req.id,
        status="success",
    )
    db.flush()
    return req


def execute_delegation(
    db: Session,
    *,
    req: DelegationRequest,
    user_id: str | None,
    mode: str = "consult",
) -> DelegationRequest:
    """
    Execute inter-agent delegation:

    1. Re-validate target capability
    2. Create child Task on target agent
    3. Run consult path (safe default) or leave pending for execute
    4. Propagate result back onto DelegationRequest
    """
    if mark_timeout_if_needed(db, req):
        raise ValueError(req.error_message or "Delegation timed out.")

    if req.status not in (
        DelegationStatus.PENDING.value,
        DelegationStatus.ACCEPTED.value,
    ):
        raise ValueError(
            f"Cannot execute delegation in status '{req.status}'."
        )

    validation = validate_delegation_target(
        db,
        company_id=req.company_id,
        target_agent_instance_id=req.target_agent_instance_id,
        required_capability=req.capability,
        source_agent_instance_id=req.source_agent_instance_id,
    )
    if not validation.valid:
        req.status = DelegationStatus.FAILED.value
        req.error_message = validation.reason
        req.completed_at = _now()
        record_audit(
            db,
            company_id=req.company_id,
            user_id=user_id,
            agent_instance_id=req.source_agent_instance_id,
            action="delegation.failed",
            resource_type="delegation_request",
            resource_id=req.id,
            status="failure",
            details={"reason": validation.reason},
        )
        db.flush()
        raise ValueError(validation.reason)

    from app.services.access import require_execution_actor
    require_execution_actor(db, company_id=req.company_id, agent_instance_id=req.target_agent_instance_id, user_id=user_id)
    req.started_at = _now()
    if req.status == DelegationStatus.PENDING.value:
        req.status = DelegationStatus.ACCEPTED.value

    # Child task on TARGET agent
    child = Task(
        company_id=req.company_id,
        agent_instance_id=req.target_agent_instance_id,
        title=f"[Delegated] {req.title}",
        instruction=req.instruction,
        mode=mode if mode in ("execute", "consult") else "consult",
        status=TaskStatus.PENDING.value,
    )
    db.add(child)
    db.flush()
    req.child_task_id = child.id

    record_audit(
        db,
        company_id=req.company_id,
        user_id=user_id,
        agent_instance_id=req.target_agent_instance_id,
        task_id=child.id,
        action="delegation.execute",
        resource_type="delegation_request",
        resource_id=req.id,
        status="success",
        details={
            "child_task_id": child.id,
            "mode": child.mode,
            "capability": req.capability,
        },
    )

    try:
        if child.mode == "consult":
            child = run_consultation(
                db,
                company_id=req.company_id,
                task_id=child.id,
                user_id=user_id,
            )
            # run_consultation commits; refresh req
            db.refresh(req)
            db.refresh(child)
            if child.status != TaskStatus.COMPLETED.value:
                raise ValueError(child.result or "Delegation child task did not complete.")
            payload = {
                "delegation_id": req.id,
                "child_task_id": child.id,
                "target_agent_instance_id": req.target_agent_instance_id,
                "capability": req.capability,
                "propagated_from_task_result": child.result,
            }
            req.result = json.dumps(payload, ensure_ascii=False)
            req.status = DelegationStatus.COMPLETED.value
            req.completed_at = _now()
            req.error_message = None
        else:
            # execute mode: child task left pending for normal task runtime
            payload = {
                "delegation_id": req.id,
                "child_task_id": child.id,
                "target_agent_instance_id": req.target_agent_instance_id,
                "capability": req.capability,
                "note": (
                    "Child task created in execute mode; "
                    "awaiting task runtime completion."
                ),
            }
            req.result = json.dumps(payload, ensure_ascii=False)
            # stay accepted until external completion callback (future)
            req.status = DelegationStatus.ACCEPTED.value

        record_audit(
            db,
            company_id=req.company_id,
            user_id=user_id,
            agent_instance_id=req.source_agent_instance_id,
            task_id=child.id,
            action="delegation.result",
            resource_type="delegation_request",
            resource_id=req.id,
            status="success",
            details={"status": req.status},
        )
        db.commit()
        db.refresh(req)
        return req

    except Exception as exc:
        req.status = DelegationStatus.FAILED.value
        req.error_message = str(exc)
        req.completed_at = _now()
        record_audit(
            db,
            company_id=req.company_id,
            user_id=user_id,
            agent_instance_id=req.target_agent_instance_id,
            task_id=req.child_task_id,
            action="delegation.failed",
            resource_type="delegation_request",
            resource_id=req.id,
            status="failure",
            details={"error": str(exc)},
        )
        db.commit()
        db.refresh(req)
        raise


def propagate_child_task_result(
    db: Session,
    *,
    req: DelegationRequest,
) -> DelegationRequest:
    """If child task completed, copy result onto delegation (for execute mode)."""
    if not req.child_task_id:
        raise ValueError("No child task linked.")
    child = db.get(Task, req.child_task_id)
    if child is None:
        raise ValueError("Child task not found.")
    if child.status != TaskStatus.COMPLETED.value:
        raise ValueError(
            f"Child task not completed (status={child.status})."
        )
    payload = {
        "delegation_id": req.id,
        "child_task_id": child.id,
        "target_agent_instance_id": req.target_agent_instance_id,
        "capability": req.capability,
        "propagated_from_task_result": child.result,
    }
    req.result = json.dumps(payload, ensure_ascii=False)
    req.status = DelegationStatus.COMPLETED.value
    req.completed_at = _now()
    record_audit(
        db,
        company_id=req.company_id,
        agent_instance_id=req.source_agent_instance_id,
        task_id=child.id,
        action="delegation.result",
        resource_type="delegation_request",
        resource_id=req.id,
        status="success",
    )
    db.commit()
    db.refresh(req)
    return req
