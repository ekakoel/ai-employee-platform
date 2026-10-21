
from unittest.mock import patch

import pytest

from app.core.config import settings
from app.llm.ollama import OllamaProvider
from app.runtime.factory import create_llm_provider


def test_factory_uses_agent_specific_ollama_model():
    with patch("app.runtime.factory.OllamaProvider") as provider_class:
        provider = create_llm_provider(
            {
                "llm_provider": "ollama",
                "llm_model": "qwen3:8b",
            }
        )

    provider_class.assert_called_once_with(
        settings,
        model="qwen3:8b",
    )
    assert provider is provider_class.return_value


def test_factory_falls_back_to_default_ollama_model():
    with patch("app.runtime.factory.OllamaProvider") as provider_class:
        create_llm_provider({"llm_provider": "ollama"})

    provider_class.assert_called_once_with(
        settings,
        model=None,
    )


def test_factory_rejects_openai_until_tool_calling_is_ready():
    with pytest.raises(ValueError, match="OpenAI is not enabled"):
        create_llm_provider(
            {
                "llm_provider": "openai",
                "llm_model": "gpt-4.1-mini",
            }
        )


def test_factory_rejects_unknown_provider():
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        create_llm_provider(
            {"llm_provider": "unknown-provider"}
        )
