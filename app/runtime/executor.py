from typing import Any
import json

from sqlalchemy.orm import Session

from app.agents.context import AgentContext
from app.llm.base import LLMProvider
from app.runtime.agent_runtime import (
    AgentRuntime,
    AgentRuntimeResult,
)
from app.runtime.tool_executor import (
    ApprovalRequiredError,
    ToolExecutionError,
    ToolExecutor,
)


class RuntimeExecutionError(Exception):
    """Raised when runtime execution fails."""


class RuntimeApprovalRequiredError(RuntimeExecutionError):
    """
    Raised when a task cannot continue until a human approves
    a tool execution.
    """

    def __init__(
        self,
        message: str,
        approval_id: str,
    ):
        super().__init__(message)
        self.approval_id = approval_id


class AgentExecutor:
    """
    AI Employee Executor.

    Supports two execution modes:

    1. Deterministic execution through execute().
       This preserves the existing runtime behavior.

    2. LLM-driven execution through execute_with_llm().
       This uses AgentRuntime and an injected LLMProvider.

    Approved actions never invoke the LLM again. They are executed
    directly through ToolExecutor using the stored approval payload.
    """

    def execute(
        self,
        db: Session,
        *,
        task_id: str,
        instruction: str,
        context: AgentContext,
    ) -> str:
        from app.services.grounding import GroundingError, MISSING_INFORMATION, requires_action, sources
        authoritative = sources(context)
        knowledge_count = len(context.knowledge)

        knowledge_summary = "\n".join(
            f"- {item['title']}: {item['content']}"
            for item in context.knowledge
        )

        if not knowledge_summary:
            knowledge_summary = (
                "- No agent-specific knowledge available."
            )

        tool_results: list[str] = []

        planned_tool = self._plan_tool(instruction)
        if planned_tool is None and requires_action(instruction):
            raise RuntimeExecutionError("No authorized deterministic workflow can perform this action. Use a configured skill and tool workflow.")
        if planned_tool is None and not authoritative:
            raise GroundingError(MISSING_INFORMATION)

        if planned_tool is not None:
            tool_name, arguments = planned_tool

            tool_executor = ToolExecutor(db)

            try:
                result = tool_executor.execute(
                    company_id=context.company_id,
                    agent_instance_id=context.agent_instance_id,
                    tool_name=tool_name,
                    arguments=arguments,
                    task_id=task_id,
                )

                tool_results.append(
                    self._format_tool_result(
                        tool_name=tool_name,
                        result=result,
                    )
                )

            except ApprovalRequiredError as exc:
                raise RuntimeApprovalRequiredError(
                    str(exc),
                    approval_id=exc.approval_id,
                ) from exc

            except ToolExecutionError as exc:
                raise RuntimeExecutionError(
                    f"Tool '{tool_name}' execution failed: {exc}"
                ) from exc

        tool_summary = "\n\n".join(tool_results)

        if not tool_summary:
            tool_summary = "No tool execution was required."

        return (
            f"Task executed by {context.agent_name}.\n\n"
            f"Task ID: {task_id}\n"
            f"Instruction: {instruction}\n\n"
            f"Agent knowledge ({knowledge_count} items):\n"
            f"{knowledge_summary}\n\n"
            f"Tool execution:\n"
            f"{tool_summary}\n\n"
            f"Runtime status: completed\n"
        )

    def execute_with_llm(
        self,
        db: Session,
        *,
        context: AgentContext,
        provider: LLMProvider,
        temperature: float = 0.0,
        max_tool_iterations: int = 5,
    ) -> AgentRuntimeResult:
        """
        Execute an AI Employee task using the LLM runtime.

        The ToolExecutor is created for the current database session.
        Its registry is passed directly to AgentRuntime so the LLM sees
        the same registered tools that the security boundary can execute.
        """

        tool_executor = ToolExecutor(db)

        from app.services.llm_usage import RecordingLLMProvider

        recorded_provider = RecordingLLMProvider(
            provider,
            db,
            company_id=context.company_id,
            agent_instance_id=context.agent_instance_id,
            task_id=context.task_id,
            enforce_budget=True,
        )

        runtime = AgentRuntime(
            provider=recorded_provider,
            tool_executor=tool_executor,
            tool_registry=tool_executor.registry,
        )

        try:
            return runtime.run_task(
                context,
                temperature=temperature,
                max_tool_iterations=max_tool_iterations,
            )

        except ApprovalRequiredError as exc:
            raise RuntimeApprovalRequiredError(
                str(exc),
                approval_id=exc.approval_id,
            ) from exc

        except ToolExecutionError as exc:
            raise RuntimeExecutionError(
                f"LLM tool execution failed: {exc}"
            ) from exc

    def execute_approved(
        self,
        db: Session,
        *,
        task_id: str,
        approval_id: str,
        context: AgentContext,
    ) -> str:
        """
        Resume a task by executing the exact action stored in an
        approved Approval record.

        The LLM/planner is intentionally NOT called again.
        """

        tool_executor = ToolExecutor(db)

        try:
            result = tool_executor.execute_approved(
                company_id=context.company_id,
                task_id=task_id,
                approval_id=approval_id,
            )

        except ToolExecutionError as exc:
            raise RuntimeExecutionError(
                f"Approved tool execution failed: {exc}"
            ) from exc

        tool_name = self._approval_tool_name(
            db,
            approval_id=approval_id,
            company_id=context.company_id,
            task_id=task_id,
        )

        tool_result = self._format_tool_result(
            tool_name=tool_name,
            result=result,
        )
        if tool_name == "draft_quotation":
            return json.dumps({"status": "verified", "tool_results": [{"tool": tool_name, "result": result}],
                               "approval_id": approval_id}, ensure_ascii=True, allow_nan=False)

        return (
            f"Task resumed by {context.agent_name}.\n\n"
            f"Task ID: {task_id}\n\n"
            f"Approved tool execution:\n"
            f"{tool_result}\n\n"
            f"Runtime status: completed\n"
        )

    def _approval_tool_name(
        self,
        db: Session,
        *,
        approval_id: str,
        company_id: str,
        task_id: str,
    ) -> str:
        from sqlalchemy import select

        from app.models.entities import Approval

        approval = db.scalar(
            select(Approval).where(
                Approval.id == approval_id,
                Approval.company_id == company_id,
                Approval.task_id == task_id,
            )
        )

        if approval is None:
            raise RuntimeExecutionError(
                "Approved request not found for this company and task."
            )

        return approval.action

    def _plan_tool(
        self,
        instruction: str,
    ) -> tuple[str, dict] | None:
        """
        Deterministic tool planner v0.1.

        This remains available for backward compatibility while
        LLM-driven execution is introduced incrementally.
        """

        normalized = instruction.lower()

        if "contract" in normalized or "kontrak" in normalized:
            return (
                "search_contract",
                {
                    "query": "contract",
                },
            )

        return None

    @staticmethod
    def _format_tool_result(
        *,
        tool_name: str,
        result: dict[str, Any],
    ) -> str:
        count = result.get("count")

        if count is not None:
            return (
                f"Tool: {tool_name}\n"
                f"Result count: {count}\n"
                f"Results: {json.dumps(result, ensure_ascii=True, allow_nan=False)}"
            )

        return (
            f"Tool: {tool_name}\n"
            f"Result: {json.dumps(result, ensure_ascii=True, allow_nan=False)}"
        )
