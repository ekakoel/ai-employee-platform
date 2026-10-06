from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.llm.base import LLMTool


@dataclass(frozen=True)
class ToolContext:
    company_id: str
    agent_instance_id: str
    task_id: str | None = None


class AgentTool(ABC):
    """Base contract for all AI Employee tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def description(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def execute(
        self,
        context: ToolContext,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        raise NotImplementedError

    def to_llm_tool(self) -> LLMTool:
        return LLMTool(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
        )