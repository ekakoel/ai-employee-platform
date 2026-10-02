from sqlalchemy.orm import Session

from app.agents.context import AgentContext
from app.runtime.tool_executor import (
    ApprovalRequiredError,
    ToolExecutionError,
    ToolExecutor,
)


class RuntimeExecutionError(Exception):
    """Raised when deterministic runtime execution fails."""


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
    Deterministic Agent Executor v0.2.

    Responsibilities:
    - Validate AgentContext.
    - Determine whether a tool is required.
    - Delegate tool execution to ToolExecutor.
    - Never bypass ToolExecutor permission checks.
    - Produce a concise execution result.

    This version does not call an LLM yet.
    """

    def execute(
        self,
        db: Session,
        *,
        task_id: str,
        instruction: str,
        context: AgentContext,
    ) -> str:
        if context.status != "active":
            raise RuntimeExecutionError(
                f"Agent '{context.agent_instance_id}' is not active."
            )

        knowledge_count = len(context.knowledge)

        knowledge_summary = "\n".join(
            f"- {item['title']}: {item['content']}"
            for item in context.knowledge
        )

        if not knowledge_summary:
            knowledge_summary = "- No agent-specific knowledge available."

        tool_results: list[str] = []

        planned_tool = self._plan_tool(instruction)

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
            f"Task executed by {context.name}.\n\n"
            f"Task ID: {task_id}\n"
            f"Instruction: {instruction}\n\n"
            f"Agent knowledge ({knowledge_count} items):\n"
            f"{knowledge_summary}\n\n"
            f"Tool execution:\n"
            f"{tool_summary}\n\n"
            f"Runtime status: completed\n"
        )

    def _plan_tool(
        self,
        instruction: str,
    ) -> tuple[str, dict] | None:
        """
        Deterministic tool planner v0.1.

        This is intentionally simple and will later be replaceable
        by an LLM/planner without changing ToolExecutor.
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

    def _format_tool_result(
        self,
        *,
        tool_name: str,
        result: dict,
    ) -> str:
        count = result.get("count")

        if count is not None:
            return (
                f"Tool: {tool_name}\n"
                f"Result count: {count}\n"
                f"Results: {result.get('results', [])}"
            )

        return (
            f"Tool: {tool_name}\n"
            f"Result: {result}"
        )