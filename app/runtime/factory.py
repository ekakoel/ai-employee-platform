from app.core.config import settings
from app.llm.base import LLMProvider
from app.llm.ollama import OllamaProvider


def create_llm_provider() -> LLMProvider:
    """
    Create the configured LLM provider for the application.

    Provider selection is controlled by Settings so API routes
    and runtime services do not depend directly on a specific
    LLM implementation.
    """

    provider_name = settings.llm_provider.strip().lower()

    if provider_name == "ollama":
        return OllamaProvider(settings)

    raise ValueError(
        f"Unsupported LLM provider: '{settings.llm_provider}'."
    )