from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMMessage:
    role: str
    content: str
    tool_call_id: str | None = None
    tool_name: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class LLMTool:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class LLMResponse:
    content: str
    model: str
    raw: Any = None


class LLMProvider(ABC):
    """Provider-agnostic interface for AI Employee LLMs."""

    @abstractmethod
    def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.0,
        tools: list[LLMTool] | None = None,
    ) -> LLMResponse:
        """Send messages to the LLM and return a normalized response."""
        raise NotImplementedError