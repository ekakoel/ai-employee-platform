
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.agents.context import load_agent_context
from app.models.entities import (
    AgentInstance,
    Approval,
    ApprovalStatus,
    Task,
    TaskStatus,
)
from app.runtime.executor import (
    AgentExecutor,
    RuntimeApprovalRequiredError,
    RuntimeExecutionError,
)
from app.services.audit import record_audit
from app.models.entities import NotificationType
from app.services.notifications import emit_notification
from app.llm.base import LLMProvider
from app.runtime.factory import create_llm_provider
from app.runtime.agent_runtime import AgentRuntimeResult



def _notify_task_failed(db, task) -> None:
    try:
        from app.models.entities import AgentInstance, NotificationType
        from app.services.notifications import emit_notification
        agent = db.get(AgentInstance, task.agent_instance_id)
        if agent and agent.supervisor_user_id:
            emit_notification(
                db,
                company_id=task.company_id,
                user_id=agent.supervisor_user_id,
                type=NotificationType.TASK_FAILED.value,
                title=f"Task failed: {task.title}",
                body=(task.result or "")[:500],
                payload={
                    "task_id": task.id,
                    "agent_instance_id": task.agent_instance_id,
                    "status": task.status,
                },
            )
    except Exception:
        pass


class TaskRuntimeService:
    def __init__(
        self,
        executor: AgentExecutor | None = None,
        provider: LLMProvider | None = None,
    ):
        self.executor = executor or AgentExecutor()
        self.provider = provider or create_llm_provider()

    def execute(
        self,
        db: Session,
        *,
        company_id: str,
        task_id: str,
    ) -> Task:
        # ---------------------------------------------------------
        # ATOMIC TASK CLAIM
        # ---------------------------------------------------------
        #
        # Only one concurrent executor can change PENDING -> PLANNING.
        #
        # This prevents:
        #
        # Request A: SELECT PENDING
        # Request B: SELECT PENDING
        # Request A: create approval
        # Request B: create approval
        #
        # The UPDATE is atomic at the database level.
        # SQLite serializes concurrent writes.
        #
        claim_result = db.execute(
            update(Task)
            .where(
                Task.id == task_id,
                Task.company_id == company_id,
                Task.status == TaskStatus.PENDING.value,
            )
            .values(
                status=TaskStatus.PLANNING.value,
            )
        )

        if claim_result.rowcount != 1:
            db.rollback()

            task = db.scalar(
                select(Task).where(
                    Task.id == task_id,
                    Task.company_id == company_id,
                )
            )

            if task is None:
                raise ValueError(
                    "Task not found for this company."
                )

            raise ValueError(
                f"Task cannot be executed from status '{task.status}'."
            )

        # ---------------------------------------------------------
        # LOAD CLAIMED TASK
        # ---------------------------------------------------------
        #
        # The claim must be committed before continuing because
        # the rest of the execution may involve another service
        # committing its own transaction, such as ApprovalService.
        #
        db.commit()

        task = db.scalar(
            select(Task).where(
                Task.id == task_id,
                Task.company_id == company_id,
            )
        )

        if task is None:
            raise ValueError(
                "Task not found for this company."
            )

        # ---------------------------------------------------------
        # PLANNING AUDIT
        # ---------------------------------------------------------
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

        db.commit()

        # ---------------------------------------------------------
        # LOAD AGENT
        # ---------------------------------------------------------
        agent = db.scalar(
            select(AgentInstance).where(
                AgentInstance.id == task.agent_instance_id,
                AgentInstance.company_id == company_id,
            )
        )

        if agent is None:
            task.status = TaskStatus.FAILED.value
            _notify_task_failed(db, task)
            task.result = (
                "Agent instance not found for this company."
            )

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
                    "error": "Agent instance not found for this company.",
                },
            )

            db.commit()
            db.refresh(task)

            raise ValueError(
                "Agent instance not found for this company."
            )

        # ---------------------------------------------------------
        # LOAD AGENT CONTEXT
        # ---------------------------------------------------------
        context = load_agent_context(
            db,
            agent,
            task,
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
                "agent_name": context.agent_name,
                "knowledge_count": len(context.knowledge),
            },
        )

        db.commit()

        # ---------------------------------------------------------
        # EXECUTION
        # ---------------------------------------------------------
        try:
            result = self.executor.execute(
                db,
                task_id=task.id,
                instruction=task.instruction,
                context=context,
            )

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
            _notify_task_failed(db, task)
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


    def reject_after_approval(
        self,
        db: Session,
        *,
        company_id: str,
        task_id: str,
        approval_id: str,
        reason: str | None = None,
    ) -> Task:
        """
        Stop a task after its approval request has been rejected.

        The task must currently be WAITING_APPROVAL and the approval
        must belong to the same company, task, and agent.

        This keeps task lifecycle transitions inside TaskRuntimeService
        instead of allowing API routes to mutate Task.status directly.
        """

        task = db.scalar(
            select(Task).where(
                Task.id == task_id,
                Task.company_id == company_id,
            )
        )

        if task is None:
            raise ValueError(
                "Task not found for this company."
            )

        if task.status != TaskStatus.WAITING_APPROVAL.value:
            raise ValueError(
                f"Task cannot be rejected from status '{task.status}'."
            )

        approval = db.scalar(
            select(Approval).where(
                Approval.id == approval_id,
                Approval.company_id == company_id,
                Approval.task_id == task_id,
            )
        )

        if approval is None:
            raise ValueError(
                "Approval not found for this company and task."
            )

        if approval.status != ApprovalStatus.REJECTED.value:
            raise ValueError(
                f"Task cannot be stopped because approval status is "
                f"'{approval.status}'."
            )

        if approval.agent_instance_id != task.agent_instance_id:
            raise ValueError(
                "Approval agent does not match the task agent."
            )

        task.status = TaskStatus.FAILED.value
        _notify_task_failed(db, task)
        task.result = (
            "Task stopped because the approval was rejected."
        )

        if reason:
            task.result += f"\nReason: {reason}"

        record_audit(
            db,
            company_id=company_id,
            agent_instance_id=task.agent_instance_id,
            task_id=task.id,
            action="task.rejected_after_approval",
            resource_type="task",
            resource_id=task.id,
            status="failed",
            details={
                "approval_id": approval.id,
                "reason": reason,
            },
        )

        db.commit()
        db.refresh(task)

        return task
    def execute_with_llm(
        self,
        db: Session,
        *,
        company_id: str,
        task_id: str,
        temperature: float = 0.0,
        max_tool_iterations: int = 5,
    ) -> Task:
        """
        Execute a task using the configured LLM runtime.

        TaskRuntimeService owns the Task lifecycle. Therefore an
        approval request raised by the LLM runtime is converted into
        WAITING_APPROVAL here.

        AgentExecutor remains responsible only for runtime execution
        and propagates runtime exceptions.
        """

        if self.provider is None:
            raise ValueError(
                "LLM provider is not configured."
            )

        task = db.scalar(
            select(Task).where(
                Task.id == task_id,
                Task.company_id == company_id,
            )
        )

        if task is None:
            raise ValueError(
                "Task not found for this company."
            )

        agent = db.scalar(
            select(AgentInstance).where(
                AgentInstance.id == task.agent_instance_id,
                AgentInstance.company_id == company_id,
            )
        )

        if agent is None:
            raise ValueError(
                "Agent instance not found for this company."
            )

        context = load_agent_context(
            db,
            agent,
            task,
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
                "agent_name": context.agent_name,
                "knowledge_count": len(context.knowledge),
                "execution_mode": "llm",
            },
        )

        db.commit()

        # ---------------------------------------------------------
        # LLM EXECUTION
        # ---------------------------------------------------------
        try:
            self.executor.execute_with_llm(
                db,
                context=context,
                provider=self.provider,
                temperature=temperature,
                max_tool_iterations=max_tool_iterations,
            )

            task = db.scalar(
                select(Task).where(
                    Task.id == task_id,
                    Task.company_id == company_id,
                )
            )

            if task is None:
                raise ValueError(
                    "Task not found after LLM execution."
                )

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
                details={
                    "execution_mode": "llm",
                },
            )

            db.commit()
            db.refresh(task)

            return task

        except RuntimeApprovalRequiredError as exc:
            # IMPORTANT:
            # ApprovalService.create_request() already commits the
            # Approval before RuntimeApprovalRequiredError is raised.
            #
            # Therefore we must NOT rollback here, otherwise the
            # newly-created approval could be lost.
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
                    "execution_mode": "llm",
                },
            )

            db.commit()
            db.refresh(task)

            return task

        except RuntimeExecutionError as exc:
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
            _notify_task_failed(db, task)
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
                    "execution_mode": "llm",
                },
            )

            db.commit()
            db.refresh(task)

            return task
    def resume_after_approval(
        self,
        db: Session,
        *,
        company_id: str,
        task_id: str,
        approval_id: str,
    ) -> Task:
        """
        Resume a task after a human approval.

        The task must be WAITING_APPROVAL and the approval must
        belong to the same company and task.

        The approval must also belong to the same agent instance
        as the task.

        The exact approved tool action is executed through
        AgentExecutor.execute_approved(). The LLM/planner is not
        called again.
        """

        task = db.scalar(
            select(Task).where(
                Task.id == task_id,
                Task.company_id == company_id,
            )
        )

        if task is None:
            raise ValueError(
                "Task not found for this company."
            )

        if task.status != TaskStatus.WAITING_APPROVAL.value:
            raise ValueError(
                f"Task cannot resume from status '{task.status}'."
            )

        approval = db.scalar(
            select(Approval).where(
                Approval.id == approval_id,
                Approval.company_id == company_id,
                Approval.task_id == task_id,
            )
        )

        if approval is None:
            raise ValueError(
                "Approval not found for this company and task."
            )

        if approval.status != ApprovalStatus.APPROVED.value:
            raise ValueError(
                f"Task cannot resume because approval status is "
                f"'{approval.status}'."
            )

        if approval.agent_instance_id != task.agent_instance_id:
            raise ValueError(
                "Approval agent does not match the task agent."
            )

        # ---------------------------------------------------------
        # ATOMIC RESUME CLAIM
        # ---------------------------------------------------------
        claim_result = db.execute(
            update(Task)
            .where(
                Task.id == task_id,
                Task.company_id == company_id,
                Task.status == TaskStatus.WAITING_APPROVAL.value,
            )
            .values(
                status=TaskStatus.RUNNING.value,
                result=None,
            )
        )

        if claim_result.rowcount != 1:
            db.rollback()

            current_task = db.scalar(
                select(Task).where(
                    Task.id == task_id,
                    Task.company_id == company_id,
                )
            )

            if current_task is None:
                raise ValueError(
                    "Task not found for this company."
                )

            raise ValueError(
                f"Task cannot resume from status "
                f"'{current_task.status}'."
            )

        db.commit()

        task = db.scalar(
            select(Task).where(
                Task.id == task_id,
                Task.company_id == company_id,
            )
        )

        if task is None:
            raise ValueError(
                "Task not found after resume claim."
            )

        # ---------------------------------------------------------
        # LOAD AGENT
        # ---------------------------------------------------------
        agent = db.scalar(
            select(AgentInstance).where(
                AgentInstance.id == task.agent_instance_id,
                AgentInstance.company_id == company_id,
            )
        )

        if agent is None:
            raise ValueError(
                "Agent instance not found for this company."
            )

        # ---------------------------------------------------------
        # LOAD AGENT CONTEXT
        # ---------------------------------------------------------
        context = load_agent_context(
            db,
            agent,
            task,
        )

        # ---------------------------------------------------------
        # RESUME AUDIT
        # ---------------------------------------------------------
        record_audit(
            db,
            company_id=company_id,
            agent_instance_id=task.agent_instance_id,
            task_id=task.id,
            action="task.resumed",
            resource_type="task",
            resource_id=task.id,
            status="success",
            details={
                "approval_id": approval.id,
                "tool": approval.action,
            },
        )

        db.commit()

        # ---------------------------------------------------------
        # APPROVED EXECUTION
        # ---------------------------------------------------------
        try:
            result = self.executor.execute_approved(
                db,
                task_id=task.id,
                approval_id=approval.id,
                context=context,
            )

            task.result = result
            task.status = TaskStatus.COMPLETED.value

            record_audit(
                db,
                company_id=company_id,
                agent_instance_id=task.agent_instance_id,
                task_id=task.id,
                action="task.completed_after_approval",
                resource_type="task",
                resource_id=task.id,
                status="success",
                details={
                    "approval_id": approval.id,
                    "tool": approval.action,
                },
            )

            db.commit()
            db.refresh(task)

            return task

        except RuntimeExecutionError as exc:
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
            _notify_task_failed(db, task)
            task.result = str(exc)

            record_audit(
                db,
                company_id=company_id,
                agent_instance_id=task.agent_instance_id,
                task_id=task.id,
                action="task.failed_after_approval",
                resource_type="task",
                resource_id=task.id,
                status="failed",
                details={
                    "approval_id": approval_id,
                    "error": str(exc),
                },
            )

            db.commit()
            db.refresh(task)

            return task
