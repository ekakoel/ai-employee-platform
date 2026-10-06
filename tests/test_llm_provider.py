from unittest.mock import Mock, patch

from app.core.config import Settings
from app.llm.base import LLMMessage, LLMProvider, LLMResponse, LLMTool
from app.llm.ollama import OllamaProvider


def test_llm_provider_contract():
    assert issubclass(OllamaProvider, LLMProvider)


def test_ollama_provider_configuration():
    settings = Settings(
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="qwen3:1.7b",
    )

    with patch("app.llm.ollama.ollama.Client") as client_class:
        provider = OllamaProvider(settings)

    client_class.assert_called_once_with(
        host="http://127.0.0.1:11434",
    )

    assert provider.model == "qwen3:1.7b"


def test_ollama_provider_chat_normalizes_response():
    settings = Settings(
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="qwen3:1.7b",
    )

    fake_client = Mock()
    fake_client.chat.return_value = {
        "message": {
            "content": "Contract found.",
        }
    }

    with patch(
        "app.llm.ollama.ollama.Client",
        return_value=fake_client,
    ):
        provider = OllamaProvider(settings)

    response = provider.chat(
        [
            LLMMessage(
                role="user",
                content="Find the contract.",
            )
        ]
    )

    assert isinstance(response, LLMResponse)
    assert response.content == "Contract found."
    assert response.model == "qwen3:1.7b"

    fake_client.chat.assert_called_once()

def test_ollama_provider_sends_tools():
    settings = Settings(
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="qwen3:1.7b",
    )

    provider = OllamaProvider(settings)

    provider.client.chat = Mock(
        return_value={
            "message": {
                "content": "I found the contract."
            }
        }
    )

    tool = LLMTool(
        name="search_contract",
        description="Search company contracts.",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Contract search query.",
                }
            },
            "required": ["query"],
        },
    )

    response = provider.chat(
        [
            LLMMessage(
                role="user",
                content="Find the Villa ABC contract.",
            )
        ],
        tools=[tool],
    )

    assert response.content == "I found the contract."

    provider.client.chat.assert_called_once()

    call_kwargs = provider.client.chat.call_args.kwargs

    assert call_kwargs["model"] == "qwen3:1.7b"

    assert call_kwargs["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "search_contract",
                "description": "Search company contracts.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Contract search query.",
                        }
                    },
                    "required": ["query"],
                },
            },
        }
    ]