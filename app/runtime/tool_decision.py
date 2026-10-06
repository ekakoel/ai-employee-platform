from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    """
    A tool call requested by the LLM.

    The LLM only proposes this call.
    Actual execution is handled by ToolExecutor.
    """

    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class AgentDecision:
    """
    Normalized decision returned by the LLM.
    """

    content: str | None = None
    tool_calls: list[ToolCall] | None = None

    @property
    def requires_tool_execution(self) -> bool:
        return bool(self.tool_calls)