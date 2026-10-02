from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AgentInstance
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
        # 1. Load agent with tenant isolation
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
        # 2. Agent must be active
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
        # 3. Tool must be allowed for this Agent
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
        # 4. Tool must exist in runtime registry
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

        # ---------------------------------------------------------
        # 5. Policy evaluation
        # ---------------------------------------------------------
        decision = self.policy_engine.evaluate(
            company_id=company_id,
            agent_instance_id=agent_instance_id,
            tool_name=tool_name,
            arguments=arguments,
        )

        # ---------------------------------------------------------
        # 5A. Policy DENY
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
        # 5B. Policy requires HUMAN APPROVAL
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

            # Create approval request.
            #
            # IMPORTANT:
            # Approval model currently does not contain policy_id,
            # therefore we intentionally do not pass policy_id here.
            approval = self.approval_service.create_request(
                company_id=company_id,
                task_id=task_id,
                agent_instance_id=agent_instance_id,
                action=tool_name,
                reason=decision.reason,
                payload=arguments,
            )

            # Do NOT treat approval requirement as a normal failure.
            # AgentExecutor / TaskRuntimeService will handle this
            # exception and move the task to waiting_approval.
            raise ApprovalRequiredError(
                f"Tool '{tool_name}' requires approval. "
                f"Approval ID: {approval.id}",
                approval_id=approval.id,
            )

        # ---------------------------------------------------------
        # 6. Execute tool
        # ---------------------------------------------------------
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