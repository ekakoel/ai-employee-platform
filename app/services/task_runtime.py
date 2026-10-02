from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.context import load_agent_context
from app.models.entities import Task, TaskStatus
from app.runtime.executor import (
    AgentExecutor,
    RuntimeApprovalRequiredError,
    RuntimeExecutionError,
)
from app.services.audit import record_audit


class TaskRuntimeService:
    def __init__(self, executor: AgentExecutor | None = None):
        self.executor = executor or AgentExecutor()

    def execute(
        self,
        db: Session,
        *,
        company_id: str,
        task_id: str,
    ) -> Task:
        task = db.scalar(
            select(Task).where(
                Task.id == task_id,
                Task.company_id == company_id,
            )
        )

        if task is None:
            raise ValueError("Task not found for this company.")

        if task.status != TaskStatus.PENDING.value:
            raise ValueError(
                f"Task cannot be executed from status '{task.status}'."
            )

        # ---------------------------------------------------------
        # PLANNING
        # ---------------------------------------------------------
        task.status = TaskStatus.PLANNING.value

        record_audit(
            db,
            company_id=company_id,
            agent_instance_id=task.agent_instance_id,
            task_id=task.id,
            action="task.planning",
            resource_type="task",
            resource_id=task.id,
            status="success",
        )

        db.flush()

        # ---------------------------------------------------------
        # LOAD AGENT CONTEXT
        # ---------------------------------------------------------
        context = load_agent_context(
            db,
            company_id=company_id,
            agent_instance_id=task.agent_instance_id,
        )

        # ---------------------------------------------------------
        # RUNNING
        # ---------------------------------------------------------
        task.status = TaskStatus.RUNNING.value

        record_audit(
            db,
            company_id=company_id,
            agent_instance_id=task.agent_instance_id,
            task_id=task.id,
            action="task.running",
            resource_type="task",
            resource_id=task.id,
            status="success",
            details={
                "agent_name": context.name,
                "knowledge_count": len(context.knowledge),
            },
        )

        db.flush()

        try:
            result = self.executor.execute(
                db,
                task_id=task.id,
                instruction=task.instruction,
                context=context,
            )

            # -----------------------------------------------------
            # COMPLETED
            # -----------------------------------------------------
            task.result = result
            task.status = TaskStatus.COMPLETED.value

            record_audit(
                db,
                company_id=company_id,
                agent_instance_id=task.agent_instance_id,
                task_id=task.id,
                action="task.completed",
                resource_type="task",
                resource_id=task.id,
                status="success",
            )

            db.commit()
            db.refresh(task)

            return task

        except RuntimeApprovalRequiredError as exc:
            # -----------------------------------------------------
            # WAITING FOR HUMAN APPROVAL
            # -----------------------------------------------------
            #
            # The ApprovalService has already persisted the
            # approval request. We now persist the task state.
            #
            db.rollback()

            task = db.scalar(
                select(Task).where(
                    Task.id == task_id,
                    Task.company_id == company_id,
                )
            )

            if task is None:
                raise

            task.status = TaskStatus.WAITING_APPROVAL.value

            task.result = (
                "Task is waiting for human approval.\n"
                f"Approval ID: {exc.approval_id}\n"
                f"Reason: {exc}"
            )

            record_audit(
                db,
                company_id=company_id,
                agent_instance_id=task.agent_instance_id,
                task_id=task.id,
                action="task.waiting_approval",
                resource_type="task",
                resource_id=task.id,
                status="waiting_approval",
                details={
                    "approval_id": exc.approval_id,
                    "reason": str(exc),
                },
            )

            db.commit()
            db.refresh(task)

            return task

        except RuntimeExecutionError as exc:
            # -----------------------------------------------------
            # FAILED
            # -----------------------------------------------------
            db.rollback()

            task = db.scalar(
                select(Task).where(
                    Task.id == task_id,
                    Task.company_id == company_id,
                )
            )

            if task is None:
                raise

            task.status = TaskStatus.FAILED.value
            task.result = str(exc)

            record_audit(
                db,
                company_id=company_id,
                agent_instance_id=task.agent_instance_id,
                task_id=task.id,
                action="task.failed",
                resource_type="task",
                resource_id=task.id,
                status="failed",
                details={
                    "error": str(exc),
                },
            )

            db.commit()
            db.refresh(task)

            return task