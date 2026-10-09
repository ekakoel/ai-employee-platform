from unittest.mock import Mock, patch

from app.llm.base import LLMProvider, LLMResponse
from app.runtime.agent_runtime import AgentRuntimeResult
from app.services.task_runtime import TaskRuntimeService
from app.models.entities import TaskStatus


class FakeLLMProvider(LLMProvider):
    def chat(
        self,
        messages,
        *,
        temperature: float = 0.0,
        tools=None,
    ) -> LLMResponse:
        return LLMResponse(
            content="Fake LLM response",
            model="fake-model",
        )


def test_task_runtime_accepts_llm_provider():
    provider = FakeLLMProvider()

    runtime = TaskRuntimeService(
        provider=provider,
    )

    assert runtime.provider is provider


def test_task_runtime_execute_with_llm_delegates_to_executor():
    provider = FakeLLMProvider()

    executor = Mock()

    task = Mock()
    task.id = "task-1"
    task.company_id = "company-1"
    task.agent_instance_id = "agent-1"
    task.status = "pending"
    task.result = None

    agent = Mock()
    agent.id = "agent-1"
    agent.company_id = "company-1"

    db = Mock()
    db.execute.return_value.rowcount = 1
    db.scalar.side_effect = [
        task,
        agent,
        task,
    ]

    context = Mock()
    context.company_id = "company-1"
    context.agent_instance_id = "agent-1"
    context.agent_name = "Test Agent"
    context.knowledge = []

    executor.execute_with_llm.return_value = AgentRuntimeResult(
        response=None, decision=None, context=context,
        output={"status": "verified", "citations": [{"source_id": "knowledge:1", "quote": "Verified fact"}]},
    )

    runtime = TaskRuntimeService(
        executor=executor,
        provider=provider,
    )

    with patch(
        "app.services.task_runtime.load_agent_context",
        return_value=context,
    ):
        result = runtime.execute_with_llm(
            db=db,
            company_id="company-1",
            task_id="task-1",
        )

    assert result is task
    assert task.status == TaskStatus.COMPLETED.value
    assert "Verified fact" in task.result

    executor.execute_with_llm.assert_called_once()

    call = executor.execute_with_llm.call_args

    assert call.kwargs["context"] is context
    assert call.kwargs["provider"] is provider
    assert call.kwargs["temperature"] == 0.0
    assert call.kwargs["max_tool_iterations"] == 5

def test_llm_approval_required_moves_task_to_waiting_approval():
    from app.runtime.executor import RuntimeApprovalRequiredError

    provider = FakeLLMProvider()

    executor = Mock()

    executor.execute_with_llm.side_effect = (
        RuntimeApprovalRequiredError(
            "Human approval required.",
            approval_id="approval-1",
        )
    )

    task = Mock()
    task.id = "task-1"
    task.company_id = "company-1"
    task.agent_instance_id = "agent-1"
    task.status = "pending"
    task.result = None

    agent = Mock()
    agent.id = "agent-1"
    agent.company_id = "company-1"

    db = Mock()
    db.execute.return_value.rowcount = 1
    db.scalar.side_effect = [
        task,
        agent,
        task,
    ]

    context = Mock()
    context.company_id = "company-1"
    context.agent_instance_id = "agent-1"
    context.agent_name = "Test Agent"
    context.knowledge = []

    runtime = TaskRuntimeService(
        executor=executor,
        provider=provider,
    )

    with patch(
        "app.services.task_runtime.load_agent_context",
        return_value=context,
    ):
        result = runtime.execute_with_llm(
            db=db,
            company_id="company-1",
            task_id="task-1",
        )

    assert result is task
    assert task.status == TaskStatus.WAITING_APPROVAL.value
    assert "approval-1" in task.result
    assert "Human approval required." in task.result

    executor.execute_with_llm.assert_called_once()
