from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

from app.llm.base import LLMTool

RiskLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class ToolContext:
    company_id: str
    agent_instance_id: str
    task_id: str | None = None


@dataclass(frozen=True)
class ToolMeta:
    """Catalog metadata for policy, consult mode, and directory."""

    name: str
    description: str
    side_effect: bool
    risk: RiskLevel = "low"
    category: str = "general"


class AgentTool(ABC):
    """Base contract for all AI Employee tools."""

    # Subclasses should override; defaults are conservative (side-effect).
    side_effect: bool = True
    risk: RiskLevel = "medium"
    category: str = "general"

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

    def meta(self) -> ToolMeta:
        return ToolMeta(
            name=self.name,
            description=self.description,
            side_effect=bool(self.side_effect),
            risk=self.risk,  # type: ignore[arg-type]
            category=self.category,
        )

    def to_llm_tool(self) -> LLMTool:
        return LLMTool(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
        )

    def to_catalog_dict(self) -> dict[str, Any]:
        m = self.meta()
        return {
            "name": m.name,
            "description": m.description,
            "side_effect": m.side_effect,
            "risk": m.risk,
            "category": m.category,
            "parameters": self.parameters,
            "read_only": not m.side_effect,
        }
