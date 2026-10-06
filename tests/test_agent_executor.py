from unittest.mock import Mock

import pytest

from app.agents.context import AgentContext
from app.runtime.executor import (
    AgentExecutor,
    RuntimeApprovalRequiredError,
    RuntimeExecutionError,
)
from app.runtime.tool_executor import (
    ApprovalRequiredError,
    ToolExecutionError,
)


def make_context() -> AgentContext:
    return AgentContext(
        company_id=1,
        company_name="Bali Kami Tour",
        agent_instance_id=10,
        agent_name="Contract Manager",
        agent_role="Contract Manager",
        skills=["contract_search", "contract_analysis"],
        allowed_tools=["search_contract"],
        task_id=100,
        task_title="Find Villa ABC contract",
        task_instruction="Find the contract for Villa ABC.",
        knowledge=[
            {
                "title": "Villa ABC Contract",
                "content": "Villa ABC contract is valid until December 2026.",
            }
        ],
    )


def test_execute_without_tool_returns_completed_result():
    db = Mock()

    executor = AgentExecutor()

    result = executor.execute(
        db,
        task_id="task-100",
        instruction="Prepare a daily activity summary.",
        context=make_context(),
    )

    assert "Task executed by Contract Manager." in result
    assert "Task ID: task-100" in result
    assert "Prepare a daily activity summary." in result
    assert "No tool execution was required." in result
    assert "Runtime status: completed" in result


def test_execute_contract_uses_search_contract_tool(monkeypatch):
    db = Mock()

    tool_executor = Mock()

    tool_executor.execute.return_value = {
        "count": 1,
        "results": [
            {
                "title": "Villa ABC Contract",
                "content": "Villa ABC contract is valid until December 2026.",
            }
        ],
    }

    monkeypatch.setattr(
        "app.runtime.executor.ToolExecutor",
        lambda _: tool_executor,
    )

    executor = AgentExecutor()

    result = executor.execute(
        db,
        task_id="task-100",
        instruction="Find the contract for Villa ABC.",
        context=make_context(),
    )

    tool_executor.execute.assert_called_once_with(
        company_id=1,
        agent_instance_id=10,
        tool_name="search_contract",
        arguments={"query": "contract"},
        task_id="task-100",
    )

    assert "Tool: search_contract" in result
    assert "Result count: 1" in result
    assert "Runtime status: completed" in result


def test_execute_propagates_approval_required_error(monkeypatch):
    db = Mock()

    tool_executor = Mock()

    tool_executor.execute.side_effect = ApprovalRequiredError(
        "Tool 'search_contract' requires approval.",
        approval_id="approval-123",
    )

    monkeypatch.setattr(
        "app.runtime.executor.ToolExecutor",
        lambda _: tool_executor,
    )

    executor = AgentExecutor()

    with pytest.raises(RuntimeApprovalRequiredError) as exc_info:
        executor.execute(
            db,
            task_id="task-100",
            instruction="Find the contract for Villa ABC.",
            context=make_context(),
        )

    assert str(exc_info.value) == (
        "Tool 'search_contract' requires approval."
    )

    assert exc_info.value.approval_id == "approval-123"

    tool_executor.execute.assert_called_once()


def test_execute_converts_tool_execution_error(monkeypatch):
    db = Mock()

    tool_executor = Mock()

    tool_executor.execute.side_effect = ToolExecutionError(
        "Tool execution failed."
    )

    monkeypatch.setattr(
        "app.runtime.executor.ToolExecutor",
        lambda _: tool_executor,
    )

    executor = AgentExecutor()

    with pytest.raises(RuntimeExecutionError) as exc_info:
        executor.execute(
            db,
            task_id="task-100",
            instruction="Find the contract for Villa ABC.",
            context=make_context(),
        )

    assert str(exc_info.value) == (
        "Tool 'search_contract' execution failed: "
        "Tool execution failed."
    )

    tool_executor.execute.assert_called_once()


def test_execute_approved_uses_approved_tool_action(monkeypatch):
    db = Mock()

    tool_executor = Mock()

    tool_executor.execute_approved.return_value = {
        "count": 1,
        "results": [
            {
                "title": "Villa ABC Contract",
                "content": "Villa ABC contract is valid until December 2026.",
            }
        ],
    }

    monkeypatch.setattr(
        "app.runtime.executor.ToolExecutor",
        lambda _: tool_executor,
    )

    approval = Mock()
    approval.action = "search_contract"

    db.scalar.return_value = approval

    executor = AgentExecutor()

    result = executor.execute_approved(
        db,
        task_id="task-100",
        approval_id="approval-123",
        context=make_context(),
    )

    tool_executor.execute_approved.assert_called_once_with(
        company_id=1,
        task_id="task-100",
        approval_id="approval-123",
    )

    assert "Task resumed by Contract Manager." in result
    assert "Approved tool execution:" in result
    assert "Tool: search_contract" in result
    assert "Runtime status: completed" in result


def test_execute_approved_converts_tool_execution_error(monkeypatch):
    db = Mock()

    tool_executor = Mock()

    tool_executor.execute_approved.side_effect = ToolExecutionError(
        "Approved execution failed."
    )

    monkeypatch.setattr(
        "app.runtime.executor.ToolExecutor",
        lambda _: tool_executor,
    )

    executor = AgentExecutor()

    with pytest.raises(RuntimeExecutionError) as exc_info:
        executor.execute_approved(
            db,
            task_id="task-100",
            approval_id="approval-123",
            context=make_context(),
        )

    assert str(exc_info.value) == (
        "Approved tool execution failed: "
        "Approved execution failed."
    )

    tool_executor.execute_approved.assert_called_once()

def test_execute_with_llm_uses_agent_runtime(monkeypatch):
    db = Mock()

    provider = Mock()

    runtime_result = Mock()

    class FakeAgentRuntime:
        def __init__(
            self,
            *,
            provider,
            tool_executor,
            tool_registry,
        ):
            assert provider is provider_instance
            assert tool_executor is not None
            assert tool_registry is tool_executor.registry

        def run_task(
            self,
            context,
            *,
            temperature,
            max_tool_iterations,
        ):
            assert context is context_instance
            assert temperature == 0.0
            assert max_tool_iterations == 5
            return runtime_result

    provider_instance = provider
    context_instance = make_context()

    tool_executor = Mock()
    tool_executor.registry = Mock()

    monkeypatch.setattr(
        "app.runtime.executor.ToolExecutor",
        lambda _: tool_executor,
    )

    monkeypatch.setattr(
        "app.runtime.executor.AgentRuntime",
        FakeAgentRuntime,
    )

    executor = AgentExecutor()

    result = executor.execute_with_llm(
        db,
        context=context_instance,
        provider=provider,
    )

    assert result is runtime_result