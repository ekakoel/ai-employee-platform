from sqlalchemy.orm import Session

from app.models import AuditLog


def record_audit(
    db: Session,
    *,
    company_id: str,
    action: str,
    resource_type: str,
    status: str,
    resource_id: str | None = None,
    user_id: str | None = None,
    agent_instance_id: str | None = None,
    task_id: str | None = None,
    details: dict | None = None,
) -> AuditLog:
    log = AuditLog(
        company_id=company_id,
        user_id=user_id,
        agent_instance_id=agent_instance_id,
        task_id=task_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        status=status,
        details=details or {},
    )
    db.add(log)
    return log
