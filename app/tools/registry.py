from __future__ import annotations

from app.llm.base import LLMTool
from app.tools.base import AgentTool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, AgentTool] = {}

    def register(self, tool: AgentTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> AgentTool | None:
        return self._tools.get(name)

    def all(self) -> list[AgentTool]:
        return list(self._tools.values())

    def catalog(self) -> list[dict]:
        return [t.to_catalog_dict() for t in self.all()]

    def llm_tools(
        self,
        allowed_tools: list[str] | None = None,
    ) -> list[LLMTool]:
        tools = self.all()
        if allowed_tools is not None:
            allowed = set(allowed_tools)
            tools = [tool for tool in tools if tool.name in allowed]
        return [tool.to_llm_tool() for tool in tools]
