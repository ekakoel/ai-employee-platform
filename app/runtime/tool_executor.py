from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    AgentInstance,
    Approval,
    ApprovalStatus,
    Task,
)
from app.services.consultation import is_read_only_tool
from app.security.policy_engine import PolicyEngine
from app.services.approval import ApprovalService
from app.services.audit import record_audit
from app.tools.base import ToolContext
from app.tools.contract import SearchContractTool
from app.tools.registry import ToolRegistry


class ToolExecutionError(Exception):
    """Raised when a tool execution is rejected or fails."""


class ApprovalRequiredError(ToolExecutionError):
    """Raised when a tool execution requires human approval."""

    def __init__(
        self,
        message: str,
        approval_id: str,
    ):
        super().__init__(message)
        self.approval_id = approval_id


class ToolExecutor:
    def __init__(self, db: Session):
        self.db = db

        # ---------------------------------------------------------
        # Tool registry
        # ---------------------------------------------------------
        self.registry = ToolRegistry()

        self.registry.register(
            SearchContractTool(db)
        )

        # ---------------------------------------------------------
        # Security / approval services
        # ---------------------------------------------------------
        self.policy_engine = PolicyEngine(db)
        self.approval_service = ApprovalService(db)

    def execute(
        self,
        *,
        company_id: str,
        agent_instance_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        task_id: str | None = None,
    ) -> dict[str, Any]:

        # ---------------------------------------------------------
        # Consultation mode: block side-effect tools early
        # ---------------------------------------------------------
        if task_id:
            task = self.db.get(Task, task_id)
            if (
                task is not None
                and task.company_id == company_id
                and getattr(task, "mode", "execute") == "consult"
                and not is_read_only_tool(tool_name)
            ):
                self._audit_denied(
                    company_id=company_id,
                    agent_instance_id=agent_instance_id,
                    task_id=task_id,
                    tool_name=tool_name,
                    reason="consultation_side_effect_blocked",
                    extra={"mode": "consult"},
                )
                self.db.commit()
                raise ToolExecutionError(
                    f"Tool '{tool_name}' is not allowed in consultation "
                    f"mode (side-effect tools are blocked)."
                )

        agent, tool = self._validate_agent_and_tool(
            company_id=company_id,
            agent_instance_id=agent_instance_id,
            tool_name=tool_name,
            task_id=task_id,
        )

        # ---------------------------------------------------------
        # Policy evaluation
        # ---------------------------------------------------------
        decision = self.policy_engine.evaluate(
            company_id=company_id,
            agent_instance_id=agent_instance_id,
            tool_name=tool_name,
            arguments=arguments,
        )

        # ---------------------------------------------------------
        # Policy DENY
        # ---------------------------------------------------------
        if decision.denied:
            self._audit_denied(
                company_id=company_id,
                agent_instance_id=agent_instance_id,
                task_id=task_id,
                tool_name=tool_name,
                reason="policy_denied",
                extra={
                    "policy_id": decision.policy_id,
                    "policy_reason": decision.reason,
                },
            )

            self.db.commit()

            raise ToolExecutionError(
                f"Tool '{tool_name}' denied by policy: "
                f"{decision.reason}"
            )

        # ---------------------------------------------------------
        # Policy requires HUMAN APPROVAL
        # ---------------------------------------------------------
        if decision.requires_approval:
            if task_id is None:
                self._audit_denied(
                    company_id=company_id,
                    agent_instance_id=agent_instance_id,
                    task_id=None,
                    tool_name=tool_name,
                    reason="approval_requires_task",
                    extra={
                        "policy_id": decision.policy_id,
                    },
                )

                self.db.commit()

                raise ToolExecutionError(
                    "Approval-required tool execution must belong "
                    "to a task."
                )

            approval = self.approval_service.create_request(
                company_id=company_id,
                task_id=task_id,
                agent_instance_id=agent_instance_id,
                action=tool_name,
                reason=decision.reason,
                payload=arguments,
            )

            raise ApprovalRequiredError(
                f"Tool '{tool_name}' requires approval. "
                f"Approval ID: {approval.id}",
                approval_id=approval.id,
            )

        # ---------------------------------------------------------
        # Normal execution
        # ---------------------------------------------------------
        return self._execute_tool(
            tool=tool,
            company_id=company_id,
            agent_instance_id=agent_instance_id,
            task_id=task_id,
            tool_name=tool_name,
            arguments=arguments,
        )

    def execute_approved(
        self,
        *,
        company_id: str,
        task_id: str,
        approval_id: str,
    ) -> dict[str, Any]:
        """
        Execute exactly the tool action stored in an approved
        approval request.

        This method is intentionally separate from execute().

        It does NOT accept arbitrary tool arguments from the caller.
        The approval record is the source of truth.

        Security is still revalidated:
        - approval belongs to company/task
        - approval is APPROVED
        - agent belongs to company
        - agent is active
        - tool is allowed for the agent
        - tool exists in registry
        - current policy does not deny the tool

        If the current policy still requires approval, the existing
        APPROVED approval authorizes this exact stored action.
        """

        # ---------------------------------------------------------
        # 1. Load approved request with tenant isolation
        # ---------------------------------------------------------
        approval = self.db.scalar(
            select(Approval).where(
                Approval.id == approval_id,
                Approval.company_id == company_id,
                Approval.task_id == task_id,
            )
        )

        if approval is None:
            raise ToolExecutionError(
                "Approved request not found for this company and task."
            )

        # ---------------------------------------------------------
        # 2. Approval must already be approved
        # ---------------------------------------------------------
        if approval.status != ApprovalStatus.APPROVED.value:
            raise ToolExecutionError(
                "Approval is not in an approved state."
            )

        # ---------------------------------------------------------
        # 3. Validate agent and tool again
        # ---------------------------------------------------------
        agent, tool = self._validate_agent_and_tool(
            company_id=company_id,
            agent_instance_id=approval.agent_instance_id,
            tool_name=approval.action,
            task_id=task_id,
        )

        # ---------------------------------------------------------
        # 4. Re-evaluate current policy
        # ---------------------------------------------------------
        decision = self.policy_engine.evaluate(
            company_id=company_id,
            agent_instance_id=approval.agent_instance_id,
            tool_name=approval.action,
            arguments=approval.payload,
        )

        # ---------------------------------------------------------
        # 5. Current policy DENY always wins
        # ---------------------------------------------------------
        if decision.denied:
            self._audit_denied(
                company_id=company_id,
                agent_instance_id=approval.agent_instance_id,
                task_id=task_id,
                tool_name=approval.action,
                reason="policy_denied_after_approval",
                extra={
                    "approval_id":approval.id,
                    "policy_id": decision.policy_id,
                    "policy_reason": decision.reason,
                },
            )

            self.db.commit()

            raise ToolExecutionError(
                f"Approved tool '{approval.action}' is now denied "
                f"by policy: {decision.reason}"
            )

        # ---------------------------------------------------------
        # 6. Execute exact approved payload
        # ---------------------------------------------------------
        result = self._execute_tool(
            tool=tool,
            company_id=company_id,
            agent_instance_id=agent.id,
            task_id=task_id,
            tool_name=approval.action,
            arguments=approval.payload,
        )

        # ---------------------------------------------------------
        # 7. Audit approved execution
        # ---------------------------------------------------------
        record_audit(
            self.db,
            company_id=company_id,
            agent_instance_id=agent.id,
            task_id=task_id,
            action="approval.executed",
            resource_type="approval",
            resource_id=approval.id,
            status="success",
            details={
                "tool": approval.action,
                "approval_id": approval.id,
                "policy_id": decision.policy_id,
                "policy_effect": decision.effect,
            },
        )

        self.db.commit()

        return result

    def _validate_agent_and_tool(
        self,
        *,
        company_id: str,
        agent_instance_id: str,
        tool_name: str,
        task_id: str | None,
    ) -> tuple[AgentInstance, Any]:
        # ---------------------------------------------------------
        # Agent tenant isolation
        # ---------------------------------------------------------
        agent = self.db.scalar(
            select(AgentInstance).where(
                AgentInstance.id == agent_instance_id,
                AgentInstance.company_id == company_id,
            )
        )

        if agent is None:
            raise ToolExecutionError(
                "Agent instance not found for this company."
            )

        # ---------------------------------------------------------
        # Agent must be active
        # ---------------------------------------------------------
        if agent.status != "active":
            self._audit_denied(
                company_id=company_id,
                agent_instance_id=agent_instance_id,
                task_id=task_id,
                tool_name=tool_name,
                reason="agent_inactive",
            )

            self.db.commit()

            raise ToolExecutionError(
                f"Agent '{agent.id}' is not active."
            )

        configuration = agent.configuration or {}

        allowed_tools = configuration.get(
            "allowed_tools",
            [],
        )

        # ---------------------------------------------------------
        # Tool must be allowed for this Agent
        # ---------------------------------------------------------
        if tool_name not in allowed_tools:
            self._audit_denied(
                company_id=company_id,
                agent_instance_id=agent_instance_id,
                task_id=task_id,
                tool_name=tool_name,
                reason="tool_not_allowed",
            )

            self.db.commit()

            raise ToolExecutionError(
                f"Tool '{tool_name}' is not allowed for this agent."
            )

        # ---------------------------------------------------------
        # Tool must exist in runtime registry
        # ---------------------------------------------------------
        tool = self.registry.get(tool_name)

        if tool is None:
            self._audit_denied(
                company_id=company_id,
                agent_instance_id=agent_instance_id,
                task_id=task_id,
                tool_name=tool_name,
                reason="tool_not_registered",
            )

            self.db.commit()

            raise ToolExecutionError(
                f"Tool '{tool_name}' is not registered."
            )

        return agent, tool

    def _execute_tool(
        self,
        *,
        tool: Any,
        company_id: str,
        agent_instance_id: str,
        task_id: str | None,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        context = ToolContext(
            company_id=company_id,
            agent_instance_id=agent_instance_id,
            task_id=task_id,
        )

        try:
            result = tool.execute(
                context,
                arguments,
            )

            record_audit(
                self.db,
                company_id=company_id,
                agent_instance_id=agent_instance_id,
                task_id=task_id,
                action="tool.execute",
                resource_type="tool",
                resource_id=tool_name,
                status="success",
                details={
                    "tool": tool_name,
                    "arguments": arguments,
                    "result_count": result.get("count"),
                },
            )

            self.db.commit()

            return result

        except Exception as exc:
            self.db.rollback()

            record_audit(
                self.db,
                company_id=company_id,
                agent_instance_id=agent_instance_id,
                task_id=task_id,
                action="tool.execute",
                resource_type="tool",
                resource_id=tool_name,
                status="failed",
                details={
                    "tool": tool_name,
                    "error": str(exc),
                },
            )

            self.db.commit()

            raise ToolExecutionError(
                f"Tool '{tool_name}' execution failed."
            ) from exc

    def _audit_denied(
        self,
        *,
        company_id: str,
        agent_instance_id: str,
        task_id: str | None,
        tool_name: str,
        reason: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        details = {
            "tool": tool_name,
            "reason": reason,
        }

        if extra:
            details.update(extra)

        record_audit(
            self.db,
            company_id=company_id,
            agent_instance_id=agent_instance_id,
            task_id=task_id,
            action="tool.execute",
            resource_type="tool",
            resource_id=tool_name,
            status="denied",
            details=details,
        )