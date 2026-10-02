from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Approval, ApprovalStatus
from app.services.audit import record_audit


class ApprovalService:
    def __init__(self, db: Session):
        self.db = db

    def create_request(
        self,
        *,
        company_id: str,
        task_id: str,
        agent_instance_id: str,
        action: str,
        reason: str,
        payload: dict | None = None,
        policy_id: str | None = None,
    ) -> Approval:
        approval = Approval(
            company_id=company_id,
            task_id=task_id,
            agent_instance_id=agent_instance_id,
            action=action,
            reason=reason,
            payload=payload or {},
            status=ApprovalStatus.PENDING.value,
        )

        self.db.add(approval)
        self.db.flush()

        record_audit(
            self.db,
            company_id=company_id,
            agent_instance_id=agent_instance_id,
            task_id=task_id,
            action="approval.requested",
            resource_type="approval",
            resource_id=approval.id,
            status="pending",
            details={
                "action": action,
                "reason": reason,
            },
        )

        self.db.commit()
        self.db.refresh(approval)

        return approval

    def approve(
        self,
        *,
        approval_id: str,
        company_id: str,
        user_id: str,
        comment: str | None = None,
    ) -> Approval:
        approval = self._get_pending(
            approval_id=approval_id,
            company_id=company_id,
        )

        approval.status = ApprovalStatus.APPROVED.value
        approval.reviewed_by = user_id
        approval.reviewed_at = datetime.now(timezone.utc)
        approval.review_comment = comment

        record_audit(
            self.db,
            company_id=company_id,
            user_id=user_id,
            agent_instance_id=approval.agent_instance_id,
            task_id=approval.task_id,
            action="approval.approved",
            resource_type="approval",
            resource_id=approval.id,
            status="success",
            details={
                "action": approval.action,
                "comment": comment,
            },
        )

        self.db.commit()
        self.db.refresh(approval)

        return approval

    def reject(
        self,
        *,
        approval_id: str,
        company_id: str,
        user_id: str,
        comment: str | None = None,
    ) -> Approval:
        approval = self._get_pending(
            approval_id=approval_id,
            company_id=company_id,
        )

        approval.status = ApprovalStatus.REJECTED.value
        approval.reviewed_by = user_id
        approval.reviewed_at = datetime.now(timezone.utc)
        approval.review_comment = comment

        record_audit(
            self.db,
            company_id=company_id,
            user_id=user_id,
            agent_instance_id=approval.agent_instance_id,
            task_id=approval.task_id,
            action="approval.rejected",
            resource_type="approval",
            resource_id=approval.id,
            status="success",
            details={
                "action": approval.action,
                "comment": comment,
            },
        )

        self.db.commit()
        self.db.refresh(approval)

        return approval

    def _get_pending(
        self,
        *,
        approval_id: str,
        company_id: str,
    ) -> Approval:
        approval = (
            self.db.query(Approval)
            .filter(
                Approval.id == approval_id,
                Approval.company_id == company_id,
            )
            .first()
        )

        if approval is None:
            raise ValueError("Approval not found.")

        if approval.status != ApprovalStatus.PENDING.value:
            raise ValueError(
                f"Approval cannot be reviewed from status '{approval.status}'."
            )

        return approval