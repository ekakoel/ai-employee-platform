import os

import pytest

from app.llm.base import LLMMessage, LLMTool
from app.llm.ollama import OllamaProvider
from app.runtime.decision_parser import LLMDecisionParser


pytestmark = pytest.mark.integration


def ollama_tests_enabled() -> bool:
    return os.getenv("RUN_OLLAMA_TESTS") == "1"


@pytest.fixture
def ollama_provider() -> OllamaProvider:
    if not ollama_tests_enabled():
        pytest.skip(
            "Ollama integration tests are disabled. "
            "Set RUN_OLLAMA_TESTS=1 to enable them."
        )

    provider = OllamaProvider()

    try:
        provider.client.list()
    except Exception as exc:
        pytest.skip(
            f"Ollama is not available at "
            f"{provider.settings.ollama_base_url}: {exc}"
        )

    return provider


def test_ollama_returns_normalized_response(
    ollama_provider: OllamaProvider,
):
    response = ollama_provider.chat(
        [
            LLMMessage(
                role="system",
                content=(
                    "You are a test assistant. "
                    "Answer briefly."
                ),
            ),
            LLMMessage(
                role="user",
                content="Reply with exactly: TOOL TEST OK",
            ),
        ],
        temperature=0.0,
    )

    assert response.model == ollama_provider.model
    assert response.content
    assert response.raw is not None


def test_ollama_can_request_search_contract_tool(
    ollama_provider: OllamaProvider,
):
    tool = LLMTool(
        name="search_contract",
        description=(
            "Search contract records. "
            "Use this tool when the user asks "
            "to find a contract."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Contract name or search phrase."
                    ),
                },
            },
            "required": ["query"],
        },
    )

    response = ollama_provider.chat(
        [
            LLMMessage(
                role="system",
                content=(
                    "You are a contract management AI Employee. "
                    "You have access to a tool named "
                    "search_contract. "
                    "When the user asks you to find a contract, "
                    "you MUST use the search_contract tool. "
                    "Do not answer from your own knowledge."
                ),
            ),
            LLMMessage(
                role="user",
                content=(
                    "Find the contract for Villa ABC."
                ),
            ),
        ],
        temperature=0.0,
        tools=[tool],
    )

    assert response.raw is not None

    parser = LLMDecisionParser()

    decision = parser.parse(response.raw)

    assert decision.requires_tool_execution is True
    assert decision.tool_calls

    tool_call = decision.tool_calls[0]

    assert tool_call.name == "search_contract"

    assert isinstance(
        tool_call.arguments,
        dict,
    )

    assert tool_call.arguments.get("query")