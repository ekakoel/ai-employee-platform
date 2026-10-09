from unittest.mock import Mock

import pytest

from app.agents.context import AgentContext
from app.llm.base import LLMResponse
from app.runtime.agent_runtime import AgentRuntime
from app.tools.base import AgentTool
from app.tools.registry import ToolRegistry
from app.runtime.tool_executor import ApprovalRequiredError


class FakeTool(AgentTool):
    @property
    def name(self) -> str:
        return "search_contract"

    @property
    def description(self) -> str:
        return "Search contract knowledge."

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
            "count": 1,
            "results": [
                {
                    "title": "Villa ABC Contract",
                    "content": (
                        "Villa ABC contract is valid "
                        "until December 2026."
                    ),
                }
            ],
        }


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
    )


def make_tool_call_response() -> LLMResponse:
    return LLMResponse(
        content="",
        model="test-model",
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


def make_final_response() -> LLMResponse:
    return LLMResponse(
        content=(
            "I found the Villa ABC contract. "
            "It is valid until December 2026."
        ),
        model="test-model",
        raw={
            "message": {
                "content": (
                    "I found the Villa ABC contract. "
                    "It is valid until December 2026."
                )
            }
        },
    )


def test_run_task_returns_immediate_final_answer():
    provider = Mock()

    provider.chat.return_value = make_final_response()

    runtime = AgentRuntime(provider)

    from app.services.grounding import GroundingError
    with pytest.raises(GroundingError, match="could not be verified"):
        runtime.run_task(make_context())

    assert provider.chat.call_count == 1


def test_run_task_executes_tool_and_returns_final_answer():
    provider = Mock()

    provider.chat.side_effect = [
        make_tool_call_response(),
        make_final_response(),
    ]

    tool_executor = Mock()

    tool_executor.execute.return_value = {
        "count": 1,
        "results": [
            {
                "title": "Villa ABC Contract",
                "content": (
                    "Villa ABC contract is valid "
                    "until December 2026."
                ),
            }
        ],
    }

    runtime = AgentRuntime(
        provider=provider,
        tool_executor=tool_executor,
    )

    result = runtime.run_task(
        make_context()
    )

    import json
    assert json.loads(result.response.content)["tool_results"][0]["result"]["count"] == 1
    assert "December 2026" in result.response.content

    assert result.decision.requires_tool_execution is False

    assert provider.chat.call_count == 2

    tool_executor.execute.assert_called_once_with(
        company_id="1",
        agent_instance_id="10",
        task_id="100",
        tool_name="search_contract",
        arguments={
            "query": "Villa ABC",
        },
    )


def test_run_task_preserves_tool_call_and_result_messages():
    provider = Mock()

    provider.chat.side_effect = [
        make_tool_call_response(),
        make_final_response(),
    ]

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
        provider=provider,
        tool_executor=tool_executor,
    )

    runtime.run_task(
        make_context()
    )

    second_call_messages = (
        provider.chat.call_args_list[1].args[0]
    )

    assert second_call_messages[-2].role == "assistant"
    assert second_call_messages[-2].tool_calls == [
        {
            "type": "function",
            "function": {
                "name": "search_contract",
                "arguments": {
                    "query": "Villa ABC",
                },
            },
        }
    ]

    assert second_call_messages[-1].role == "tool"
    assert (
        second_call_messages[-1].tool_name
        == "search_contract"
    )

    assert (
        "Villa ABC Contract"
        in second_call_messages[-1].content
    )


def test_run_task_passes_allowed_tools_on_every_iteration():
    registry = ToolRegistry()

    registry.register(
        FakeTool()
    )

    provider = Mock()

    provider.chat.side_effect = [
        make_tool_call_response(),
        make_final_response(),
    ]

    tool_executor = Mock()

    tool_executor.execute.return_value = {
        "count": 1,
        "results": [],
    }

    runtime = AgentRuntime(
        provider=provider,
        tool_executor=tool_executor,
        tool_registry=registry,
    )

    runtime.run_task(
        make_context()
    )

    assert provider.chat.call_count == 2

    for call in provider.chat.call_args_list:
        tools = call.kwargs["tools"]

        assert tools is not None
        assert len(tools) == 1
        assert tools[0].name == "search_contract"


def test_run_task_requires_tool_executor():
    provider = Mock()

    provider.chat.return_value = make_tool_call_response()

    runtime = AgentRuntime(provider)

    with pytest.raises(RuntimeError):
        runtime.run_task(
            make_context()
        )


def test_run_task_respects_max_tool_iterations():
    provider = Mock()

    provider.chat.return_value = make_tool_call_response()

    tool_executor = Mock()

    tool_executor.execute.return_value = {
        "count": 1,
        "results": [],
    }

    runtime = AgentRuntime(
        provider=provider,
        tool_executor=tool_executor,
    )

    with pytest.raises(
        RuntimeError,
        match="Maximum tool execution iterations",
    ):
        runtime.run_task(
            make_context(),
            max_tool_iterations=2,
        )

    assert provider.chat.call_count == 2

    assert tool_executor.execute.call_count == 1


def test_run_task_rejects_invalid_max_tool_iterations():
    provider = Mock()

    runtime = AgentRuntime(provider)

    with pytest.raises(
        ValueError,
        match="max_tool_iterations",
    ):
        runtime.run_task(
            make_context(),
            max_tool_iterations=0,
        )

def test_run_task_propagates_approval_required_error():
    provider = Mock()

    provider.chat.return_value = make_tool_call_response()

    tool_executor = Mock()

    tool_executor.execute.side_effect = ApprovalRequiredError(
        "Tool 'search_contract' requires approval.",
        approval_id="approval-123",
    )

    runtime = AgentRuntime(
        provider=provider,
        tool_executor=tool_executor,
    )

    with pytest.raises(ApprovalRequiredError) as exc_info:
        runtime.run_task(
            make_context()
        )

    assert str(exc_info.value) == (
        "Tool 'search_contract' requires approval."
    )

    assert exc_info.value.approval_id == "approval-123"

    tool_executor.execute.assert_called_once()
