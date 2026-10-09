from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.entities import (
    AgentInstance,
    Approval,
    ApprovalStatus,
    AuditLog,
    Department,
    Task,
)
from app.services.consultation import is_read_only_tool
from app.security.policy_engine import PolicyEngine
from app.services.approval import ApprovalService
from app.services.audit import record_audit
from app.tools.base import ToolContext
from app.tools.domain import build_default_tools
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
        for tool in build_default_tools(db):
            self.registry.register(tool)

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
        if task_id:
            waiting = self.db.scalar(select(Task).where(
                Task.id == task_id, Task.company_id == company_id,
                Task.agent_instance_id == agent_instance_id,
                Task.status == "waiting_approval",
            ))
            pending = self.db.scalar(select(Approval.id).where(
                Approval.company_id == company_id, Approval.task_id == task_id,
                Approval.status == ApprovalStatus.PENDING.value,
            ).limit(1))
            if waiting is not None or pending is not None:
                raise ToolExecutionError("Task is waiting for approval; resume only the approved stored action.")
        # ---------------------------------------------------------
        # Consultation mode: block side-effect tools early
        # ---------------------------------------------------------
        if task_id:
            task = self.db.get(Task, task_id)
            if (
                task is not None
                and task.company_id == company_id
                and getattr(task, "mode", "execute") == "consult"
                and not is_read_only_tool(tool_name, self.registry)
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
        arguments = self._prepare_arguments(tool, company_id, agent_instance_id, task_id, arguments)

        # ---------------------------------------------------------
        # Policy evaluation
        # ---------------------------------------------------------
        decision = self.policy_engine.evaluate(
            company_id=company_id,
            agent_instance_id=agent_instance_id,
            tool_name=tool_name,
            arguments=self._policy_arguments(agent, tool, arguments),
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
                policy_id=decision.policy_id,
                approval_level=decision.approval_level,
                route_to_role=decision.route_to_role,
                route_to_user_id=decision.route_to_user_id,
                route_explanation=decision.route_explanation,
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
        self._prepare_arguments(tool, company_id, approval.agent_instance_id, task_id, approval.payload)

        # ---------------------------------------------------------
        # 4. Re-evaluate current policy
        # ---------------------------------------------------------
        decision = self.policy_engine.evaluate(
            company_id=company_id,
            agent_instance_id=approval.agent_instance_id,
            tool_name=approval.action,
            arguments=self._policy_arguments(agent, tool, approval.payload),
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

        # Reserve the stored approval before the external side effect. An interrupted
        # execution requires reconciliation, not a blind retry of the same action.
        executed = select(AuditLog.id).where(
            AuditLog.company_id == company_id, AuditLog.resource_id == approval_id,
            AuditLog.action == "approval.executed",
        ).exists()
        claim = self.db.execute(update(Approval).where(
            Approval.id == approval_id, Approval.company_id == company_id,
            Approval.task_id == task_id, Approval.status == ApprovalStatus.APPROVED.value,
            ~executed,
        ).values(status="executing"))
        if claim.rowcount != 1:
            self.db.rollback()
            raise ToolExecutionError("Approval has already been executed or claimed.")
        self.db.commit()

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
        approval.status = ApprovalStatus.APPROVED.value
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
        if agent.company is None or not agent.company.is_active:
            raise ToolExecutionError("Agent company is not active.")
        if task_id:
            task = self.db.scalar(select(Task).where(
                Task.id == task_id, Task.company_id == company_id,
                Task.agent_instance_id == agent_instance_id,
            ))
            if task is None:
                raise ToolExecutionError("Task does not belong to this company and employee.")
            if task.status not in {"pending", "planning", "running", "waiting_approval"}:
                raise ToolExecutionError("Tools cannot execute for a terminal task.")
            from app.services.scope_guard import check_scope
            match = check_scope(self.db, company_id=company_id, agent=agent, instruction=task.instruction)
            if not match.in_scope:
                raise ToolExecutionError("Tool request is outside the employee scope.")
        if agent.subscription is not None and agent.subscription.status != "active":
            raise ToolExecutionError("Agent subscription is not active.")

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

        from app.services.grounding import authorized_tools
        allowed_tools = authorized_tools(agent)
        from app.services.skills import load_assigned_skills, skill_tool_union
        skills = load_assigned_skills(self.db, company_id=company_id, agent_instance_id=agent_instance_id)
        if skills:
            allowed_tools = [name for name in allowed_tools if name in skill_tool_union(skills)]

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

        if tool.side_effect and not task_id:
            raise ToolExecutionError("Business actions must belong to an authorized task.")
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
            db=self.db,
        )

        try:
            if not isinstance(arguments, dict):
                raise ValueError("Tool arguments must be an object.")
            for key in tool.parameters.get("required", []):
                if key not in arguments or arguments[key] is None or arguments[key] == "":
                    raise ValueError(f"Missing required tool argument: {key}")
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
                    "result": result,
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

    def _prepare_arguments(self, tool, company_id, agent_id, task_id, arguments):
        try:
            if not isinstance(arguments, dict):
                raise ValueError("Tool arguments must be an object.")
            for key in tool.parameters.get("required", []):
                if key not in arguments or arguments[key] is None or arguments[key] == "":
                    raise ValueError(f"Missing required tool argument: {key}")
            prepare = getattr(tool, "prepare_arguments", None)
            if prepare is not None:
                return prepare(ToolContext(company_id=company_id, agent_instance_id=agent_id, task_id=task_id, db=self.db), arguments)
            return dict(arguments)
        except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
            self._audit_denied(company_id=company_id, agent_instance_id=agent_id, task_id=task_id,
                               tool_name=tool.name, reason="invalid_or_unverified_arguments", extra={"error": str(exc)})
            self.db.commit()
            raise ToolExecutionError(str(exc)) from exc

    def _policy_arguments(self, agent, tool, arguments):
        department = self.db.scalar(select(Department).where(
            Department.id == agent.department_id, Department.company_id == agent.company_id,
        )) if agent.department_id else None
        return {**arguments, "risk": tool.risk, "action": tool.name,
                "department": department.name if department else "",
                "department_id": department.id if department else ""}

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
