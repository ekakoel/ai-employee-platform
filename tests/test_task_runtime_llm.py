from unittest.mock import Mock, patch

from app.llm.base import LLMProvider, LLMResponse
from app.runtime.agent_runtime import AgentRuntimeResult
from app.services.task_runtime import TaskRuntimeService


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

    expected_result = Mock(spec=AgentRuntimeResult)
    executor.execute_with_llm.return_value = expected_result

    task = Mock()
    task.company_id = "company-1"
    task.agent_instance_id = "agent-1"

    agent = Mock()
    agent.id = "agent-1"
    agent.company_id = "company-1"

    db = Mock()
    db.scalar.side_effect = [
        task,
        agent,
    ]

    context = Mock()
    context.company_id = "company-1"
    context.agent_instance_id = "agent-1"

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

    assert result is expected_result

    executor.execute_with_llm.assert_called_once()

    call = executor.execute_with_llm.call_args

    assert call.kwargs["context"] is context
    assert call.kwargs["provider"] is provider
    assert call.kwargs["temperature"] == 0.0
    assert call.kwargs["max_tool_iterations"] == 5

def test_llm_approval_required_is_propagated_as_runtime_approval():
    from app.runtime.executor import RuntimeApprovalRequiredError

    provider = FakeLLMProvider()

    executor = Mock()

    executor.execute_with_llm.side_effect = RuntimeApprovalRequiredError(
        "Human approval required.",
        approval_id="approval-1",
    )

    task = Mock()
    task.company_id = "company-1"
    task.agent_instance_id = "agent-1"

    agent = Mock()
    agent.id = "agent-1"
    agent.company_id = "company-1"

    db = Mock()
    db.scalar.side_effect = [
        task,
        agent,
    ]

    context = Mock()
    context.company_id = "company-1"
    context.agent_instance_id = "agent-1"

    runtime = TaskRuntimeService(
        executor=executor,
        provider=provider,
    )

    with patch(
        "app.services.task_runtime.load_agent_context",
        return_value=context,
    ):
        try:
            runtime.execute_with_llm(
                db=db,
                company_id="company-1",
                task_id="task-1",
            )
        except RuntimeApprovalRequiredError as exc:
            assert exc.approval_id == "approval-1"
        else:
            raise AssertionError(
                "RuntimeApprovalRequiredError was not propagated."
            )