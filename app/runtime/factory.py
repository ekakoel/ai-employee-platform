
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.core.config import settings
from app.llm.base import LLMProvider
from app.llm.ollama import OllamaProvider


def create_llm_provider(
    configuration: Mapping[str, Any] | None = None,
) -> LLMProvider:
    """
    Create an LLM provider using application or agent-specific settings.

    Supported agent configuration:
        llm_provider: Provider name, for example "ollama".
        llm_model: Optional model override for this agent.

    The global application settings are not modified.
    """
    config = configuration or {}

    provider_name = str(
        config.get("llm_provider") or settings.llm_provider
    ).strip().lower()

    if provider_name == "ollama":
        raw_model = config.get("llm_model")
        model: str | None = None

        if raw_model is not None:
            normalized_model = str(raw_model).strip()
            if normalized_model:
                model = normalized_model

        return OllamaProvider(settings, model=model)

    if provider_name == "openai":
        raise ValueError(
            "OpenAI is not enabled until tool calling is ready."
        )

    raise ValueError(
        f"Unsupported LLM provider: '{provider_name}'."
    )
