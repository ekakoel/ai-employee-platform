from unittest.mock import Mock

import pytest

from app.agents.context import AgentContext
from app.llm.base import LLMMessage, LLMResponse
from app.runtime.agent_runtime import AgentRuntime
from app.tools.base import AgentTool
from app.tools.registry import ToolRegistry


class FakeTool(AgentTool):
    def __init__(
        self,
        tool_name: str,
    ) -> None:
        self._name = tool_name

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"{self._name} test tool."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                },
            },
            "required": ["query"],
        }

    def execute(
        self,
        context,
        arguments: dict,
    ) -> dict:
        return {
            "tool": self.name,
            "count": 0,
            "results": [],
        }


class FakeProvider:
    def __init__(self) -> None:
        self.last_tools = None
        self.last_messages = None

    def chat(
        self,
        messages,
        *,
        temperature=0.0,
        tools=None,
    ):
        self.last_messages = messages
        self.last_tools = tools

        return LLMResponse(
            content="Test response.",
            model="test-model",
            raw={
                "message": {
                    "content": "Test response.",
                }
            },
        )


def make_context() -> AgentContext:
    return AgentContext(
        company_id=1,
        company_name="Bali Kami Tour",
        agent_instance_id=10,
        agent_name="Contract Manager",
        agent_role="Contract Manager",
        skills=[
            "contract_search",
            "contract_analysis",
        ],
        allowed_tools=[
            "search_contract",
        ],
        task_id=100,
        task_title="Find Villa ABC contract",
        task_instruction="Find the contract for Villa ABC.",
        knowledge=[
            {
                "title": "Villa ABC Contract",
                "category": "contract",
                "content": (
                    "Villa ABC contract is valid until "
                    "December 2026."
                ),
            }
        ],
    )


def test_runtime_builds_system_message():
    provider = Mock()

    runtime = AgentRuntime(provider)

    message = runtime.build_system_message(
        make_context()
    )

    assert message.role == "system"
    assert "Contract Manager" in message.content
    assert "Bali Kami Tour" in message.content
    assert "contract_search" in message.content
    assert "search_contract" in message.content


def test_runtime_builds_task_message():
    provider = Mock()

    runtime = AgentRuntime(provider)

    message = runtime.build_task_message(
        make_context()
    )

    assert message.role == "user"
    assert "Find Villa ABC contract" in message.content
    assert (
        "Find the contract for Villa ABC."
        in message.content
    )
    assert "Villa ABC Contract" in message.content
    assert "December 2026" in message.content


def test_runtime_returns_final_answer_decision():
    provider = Mock()

    provider.chat.return_value = LLMResponse(
        content="I found the Villa ABC contract.",
        model="qwen3:1.7b",
        raw={
            "message": {
                "content": (
                    "I found the Villa ABC contract."
                )
            }
        },
    )

    runtime = AgentRuntime(provider)

    result = runtime.run(
        make_context()
    )

    from app.services.grounding import MISSING_INFORMATION
    assert result.response.content == MISSING_INFORMATION
    assert result.decision.content == MISSING_INFORMATION
    assert result.output["status"] == "insufficient_information"

    assert result.decision.tool_calls == []

    assert (
        result.decision.requires_tool_execution
        is False
    )


def test_runtime_returns_tool_decision():
    provider = Mock()

    provider.chat.return_value = LLMResponse(
        content="",
        model="qwen3:1.7b",
        raw={
            "message": {
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "search_contract",
                            "arguments": {
                                "query": "Villa ABC",
                            },
                        }
                    }
                ],
            }
        },
    )

    runtime = AgentRuntime(provider)

    result = runtime.run(
        make_context()
    )

    assert result.decision.requires_tool_execution is True

    assert len(result.decision.tool_calls) == 1

    tool_call = result.decision.tool_calls[0]

    assert tool_call.name == "search_contract"

    assert tool_call.arguments == {
        "query": "Villa ABC",
    }


def test_runtime_passes_context_to_result():
    provider = Mock()

    provider.chat.return_value = LLMResponse(
        content="Contract found.",
        model="qwen3:1.7b",
        raw={
            "message": {
                "content": "Contract found.",
            }
        },
    )

    runtime = AgentRuntime(provider)

    context = make_context()

    result = runtime.run(context)

    assert result.context is context


def test_runtime_executes_tool_through_tool_executor():
    provider = Mock()

    tool_executor = Mock()

    tool_executor.execute.return_value = {
        "count": 1,
        "results": [
            {
                "title": "Villa ABC Contract",
            }
        ],
    }

    runtime = AgentRuntime(
        provider,
        tool_executor=tool_executor,
    )

    context = make_context()

    result = runtime.execute_tool_call(
        context,
        "search_contract",
        {
            "query": "Villa ABC",
        },
    )

    assert result["count"] == 1

    tool_executor.execute.assert_called_once_with(
        company_id="1",
        agent_instance_id="10",
        task_id="100",
        tool_name="search_contract",
        arguments={
            "query": "Villa ABC",
        },
    )


def test_runtime_requires_tool_executor():
    provider = Mock()

    runtime = AgentRuntime(provider)

    with pytest.raises(RuntimeError):
        runtime.execute_tool_call(
            make_context(),
            "search_contract",
            {
                "query": "Villa ABC",
            },
        )


def test_runtime_continues_with_tool_result():
    provider = Mock()

    provider.chat.return_value = LLMResponse(
        content="The Villa ABC contract was found.",
        model="test-model",
        raw={
            "message": {
                "content": "The Villa ABC contract was found."
            }
        },
    )

    runtime = AgentRuntime(provider)

    context = make_context()

    messages = [
        runtime.build_system_message(context),
        runtime.build_task_message(context),
    ]

    result = runtime.continue_with_tool_result(
        context,
        original_messages=messages,
        tool_name="search_contract",
        tool_result={
            "count": 1,
            "results": [
                {
                    "title": "Villa ABC Contract",
                }
            ],
        },
    )

    from app.services.grounding import MISSING_INFORMATION
    assert result.response.content == MISSING_INFORMATION
    assert result.decision.content == MISSING_INFORMATION
    assert result.output["status"] == "insufficient_information"

    assert result.decision.tool_calls == []

    assert provider.chat.call_count == 1

    sent_messages = provider.chat.call_args.args[0]

    assert sent_messages[-1].role == "tool"
    assert "search_contract" in sent_messages[-1].content
    assert "Villa ABC Contract" in sent_messages[-1].content


def test_agent_runtime_passes_allowed_tools_to_provider():
    registry = ToolRegistry()

    tool = FakeTool("search_contract")
    registry.register(tool)

    provider = FakeProvider()

    runtime = AgentRuntime(
        provider=provider,
        tool_registry=registry,
    )

    context = AgentContext(
        company_id=1,
        company_name="Bali Kami",
        agent_instance_id=10,
        agent_name="Contract Manager",
        agent_role="Contract Manager",
        allowed_tools=[tool.name],
    )

    runtime.run(context)

    assert provider.last_tools is not None
    assert len(provider.last_tools) == 1
    assert provider.last_tools[0].name == "search_contract"


def test_agent_runtime_does_not_pass_unallowed_tools():
    registry = ToolRegistry()

    registry.register(
        FakeTool("search_contract")
    )

    registry.register(
        FakeTool("create_contract")
    )

    registry.register(
        FakeTool("delete_contract")
    )

    provider = FakeProvider()

    runtime = AgentRuntime(
        provider=provider,
        tool_registry=registry,
    )

    context = AgentContext(
        company_id=1,
        company_name="Bali Kami",
        agent_instance_id=10,
        agent_name="Contract Manager",
        agent_role="Contract Manager",
        allowed_tools=[
            "search_contract",
        ],
    )

    runtime.run(context)

    assert provider.last_tools is not None

    tool_names = [
        tool.name
        for tool in provider.last_tools
    ]

    assert tool_names == [
        "search_contract",
    ]

    assert "create_contract" not in tool_names
    assert "delete_contract" not in tool_names


def test_agent_runtime_passes_no_tools_when_registry_is_empty():
    registry = ToolRegistry()

    provider = FakeProvider()

    runtime = AgentRuntime(
        provider=provider,
        tool_registry=registry,
    )

    context = AgentContext(
        company_id=1,
        company_name="Bali Kami",
        agent_instance_id=10,
        agent_name="Contract Manager",
        agent_role="Contract Manager",
        allowed_tools=[
            "search_contract",
        ],
    )

    runtime.run(context)

    assert provider.last_tools == []


def test_agent_runtime_passes_no_tools_without_registry():
    provider = FakeProvider()

    runtime = AgentRuntime(
        provider=provider,
    )

    context = AgentContext(
        company_id=1,
        company_name="Bali Kami",
        agent_instance_id=10,
        agent_name="Contract Manager",
        agent_role="Contract Manager",
        allowed_tools=[
            "search_contract",
        ],
    )

    runtime.run(context)

    assert provider.last_tools is None


def test_continue_with_tool_result_preserves_allowed_tools():
    registry = ToolRegistry()

    registry.register(
        FakeTool("search_contract")
    )

    registry.register(
        FakeTool("delete_contract")
    )

    provider = FakeProvider()

    runtime = AgentRuntime(
        provider=provider,
        tool_registry=registry,
    )

    context = AgentContext(
        company_id=1,
        company_name="Bali Kami",
        agent_instance_id=10,
        agent_name="Contract Manager",
        agent_role="Contract Manager",
        allowed_tools=[
            "search_contract",
        ],
    )

    messages = [
        runtime.build_system_message(context),
        runtime.build_task_message(context),
    ]

    runtime.continue_with_tool_result(
        context,
        original_messages=messages,
        tool_name="search_contract",
        tool_result={
            "count": 1,
            "results": [
                {
                    "title": "Villa ABC Contract",
                }
            ],
        },
    )

    assert provider.last_tools is not None

    tool_names = [
        tool.name
        for tool in provider.last_tools
    ]

    assert tool_names == [
        "search_contract",
    ]

    assert "delete_contract" not in tool_names
