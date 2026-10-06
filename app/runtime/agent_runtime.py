from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.context import AgentContext
from app.llm.base import LLMMessage, LLMProvider, LLMResponse
from app.runtime.decision_parser import LLMDecisionParser
from app.runtime.tool_decision import AgentDecision, ToolCall
from app.runtime.tool_executor import ToolExecutor
from app.tools.registry import ToolRegistry


@dataclass(frozen=True)
class AgentRuntimeResult:
    """
    Result returned by one AI Employee reasoning step.
    """

    response: LLMResponse
    decision: AgentDecision
    context: AgentContext


class AgentRuntime:
    """
    Core reasoning runtime for an AI Employee.

    Responsibilities:
    - build LLM messages
    - determine available tools from AgentContext
    - pass allowed tool schemas to the LLM provider
    - call the LLM provider
    - normalize the LLM response
    - determine whether tools are requested
    - execute bounded tool loops through ToolExecutor

    Security and policy decisions remain inside ToolExecutor.
    """

    def __init__(
        self,
        provider: LLMProvider,
        decision_parser: LLMDecisionParser | None = None,
        tool_executor: ToolExecutor | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self.provider = provider
        self.decision_parser = (
            decision_parser or LLMDecisionParser()
        )
        self.tool_executor = tool_executor
        self.tool_registry = tool_registry

    def build_system_message(
        self,
        context: AgentContext,
    ) -> LLMMessage:

        agent = context.to_dict()["agent"]
        company = context.to_dict()["company"]

        return LLMMessage(
            role="system",
            content=(
                f"You are {agent['name']}, an AI Employee working "
                f"for {company['name']}.\n\n"
                f"Your role is: {agent['role']}.\n\n"
                "Your skills are:\n"
                f"{self._format_list(agent['skills'])}\n\n"
                "Your allowed tools are:\n"
                f"{self._format_list(agent['allowed_tools'])}\n\n"
                "Follow the company context and task provided to "
                "you. Do not invent information that is not present "
                "in the provided context or returned by an approved "
                "tool."
            ),
        )

    def build_task_message(
        self,
        context: AgentContext,
    ) -> LLMMessage:

        task = context.to_dict()["task"]
        knowledge = context.to_dict()["knowledge"]

        knowledge_text = self._format_knowledge(
            knowledge
        )

        content = (
            f"Task title: {task['title'] or 'Untitled task'}\n\n"
            "Task instruction:\n"
            f"{task['instruction'] or ''}\n\n"
            "Available knowledge:\n"
            f"{knowledge_text}"
        )

        return LLMMessage(
            role="user",
            content=content,
        )

    def get_allowed_llm_tools(
        self,
        context: AgentContext,
    ):
        """
        Return only the tools allowed by the AgentContext.
        """

        if self.tool_registry is None:
            return None

        return self.tool_registry.llm_tools(
            context.allowed_tools
        )

    def run(
        self,
        context: AgentContext,
        *,
        temperature: float = 0.0,
    ) -> AgentRuntimeResult:
        """
        Execute exactly one LLM reasoning step.

        This method does not automatically execute tools.
        """

        messages = [
            self.build_system_message(context),
            self.build_task_message(context),
        ]

        response = self.provider.chat(
            messages,
            temperature=temperature,
            tools=self.get_allowed_llm_tools(context),
        )

        return self._build_runtime_result(
            context=context,
            response=response,
        )

    def run_task(
        self,
        context: AgentContext,
        *,
        temperature: float = 0.0,
        max_tool_iterations: int = 5,
    ) -> AgentRuntimeResult:
        """
        Execute a bounded AI Employee task.

        The runtime repeatedly performs:

            LLM reasoning
                ↓
            tool call
                ↓
            ToolExecutor
                ↓
            tool result
                ↓
            LLM reasoning

        The loop stops when the LLM returns a final answer.

        Tool execution is always delegated to ToolExecutor.
        """

        if max_tool_iterations < 1:
            raise ValueError(
                "max_tool_iterations must be at least 1."
            )

        messages = [
            self.build_system_message(context),
            self.build_task_message(context),
        ]

        for iteration in range(max_tool_iterations):
            response = self.provider.chat(
                messages,
                temperature=temperature,
                tools=self.get_allowed_llm_tools(context),
            )

            result = self._build_runtime_result(
                context=context,
                response=response,
            )

            if not result.decision.requires_tool_execution:
                return result

            if iteration >= max_tool_iterations - 1:
                raise RuntimeError(
                    "Maximum tool execution iterations reached "
                    "before the AI Employee produced a final answer."
                )

            tool_calls = result.decision.tool_calls or []

            messages.append(
                self._build_assistant_tool_call_message(
                    tool_calls
                )
            )

            for tool_call in tool_calls:
                tool_result = self.execute_tool_call(
                    context,
                    tool_call.name,
                    tool_call.arguments,
                )

                messages.append(
                    self._build_tool_result_message(
                        tool_call.name,
                        tool_result,
                    )
                )

        raise RuntimeError(
            "AI Employee task loop terminated unexpectedly."
        )

    def execute_tool_call(
        self,
        context: AgentContext,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute a tool through the security boundary.

        AgentRuntime does not bypass ToolExecutor.
        """

        if self.tool_executor is None:
            raise RuntimeError(
                "ToolExecutor is not configured."
            )

        return self.tool_executor.execute(
            company_id=str(context.company_id),
            agent_instance_id=str(context.agent_instance_id),
            task_id=(
                str(context.task_id)
                if context.task_id is not None
                else None
            ),
            tool_name=tool_name,
            arguments=arguments,
        )

    def continue_with_tool_result(
        self,
        context: AgentContext,
        *,
        original_messages: list[LLMMessage],
        tool_name: str,
        tool_result: dict[str, Any],
        temperature: float = 0.0,
    ) -> AgentRuntimeResult:
        """
        Continue reasoning after a single tool result.
        """

        messages = [
            *original_messages,
            self._build_tool_result_message(
                tool_name,
                tool_result,
            ),
        ]

        response = self.provider.chat(
            messages,
            temperature=temperature,
            tools=self.get_allowed_llm_tools(context),
        )

        return self._build_runtime_result(
            context=context,
            response=response,
        )

    def _build_runtime_result(
        self,
        *,
        context: AgentContext,
        response: LLMResponse,
    ) -> AgentRuntimeResult:

        decision = self.decision_parser.parse(
            response.raw
            if response.raw is not None
            else response
        )

        return AgentRuntimeResult(
            response=response,
            decision=decision,
            context=context,
        )

    @staticmethod
    def _build_assistant_tool_call_message(
        tool_calls: list[ToolCall],
    ) -> LLMMessage:

        return LLMMessage(
            role="assistant",
            content="",
            tool_calls=[
                {
                    "type": "function",
                    "function": {
                        "name": tool_call.name,
                        "arguments": tool_call.arguments,
                    },
                }
                for tool_call in tool_calls
            ],
        )

    @staticmethod
    def _build_tool_result_message(
        tool_name: str,
        tool_result: dict[str, Any],
    ) -> LLMMessage:

        return LLMMessage(
            role="tool",
            content=AgentRuntime._format_tool_result(
                tool_name,
                tool_result,
            ),
            tool_name=tool_name,
        )

    @staticmethod
    def _format_list(
        items: list[str],
    ) -> str:

        if not items:
            return "- None"

        return "\n".join(
            f"- {item}"
            for item in items
        )

    @staticmethod
    def _format_knowledge(
        knowledge: list[dict],
    ) -> str:

        if not knowledge:
            return "No knowledge is currently available."

        sections: list[str] = []

        for item in knowledge:
            title = item.get("title") or "Untitled"
            category = item.get("category") or "general"
            content = item.get("content") or ""

            sections.append(
                f"[{category}] {title}\n"
                f"{content}"
            )

        return "\n\n".join(sections)

    @staticmethod
    def _format_tool_result(
        tool_name: str,
        tool_result: dict[str, Any],
    ) -> str:

        return (
            f"Tool executed: {tool_name}\n\n"
            "Tool result:\n"
            f"{tool_result}"
        )