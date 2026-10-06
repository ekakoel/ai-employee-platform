from unittest.mock import Mock

from app.tools.base import AgentTool
from app.tools.registry import ToolRegistry


class DummyTool(AgentTool):
    @property
    def name(self) -> str:
        return "dummy_tool"

    @property
    def description(self) -> str:
        return "A dummy test tool."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "value": {
                    "type": "string",
                }
            },
            "required": ["value"],
        }

    def execute(
        self,
        context,
        arguments,
    ) -> dict:
        return {
            "value": arguments["value"],
        }


def test_registry_generates_llm_tools():
    registry = ToolRegistry()

    registry.register(DummyTool())

    tools = registry.llm_tools()

    assert len(tools) == 1

    assert tools[0].name == "dummy_tool"
    assert tools[0].description == "A dummy test tool."

    assert tools[0].parameters["type"] == "object"


def test_registry_filters_llm_tools_by_allowed_tools():
    registry = ToolRegistry()

    registry.register(DummyTool())

    another_tool = Mock(spec=AgentTool)
    another_tool.name = "another_tool"
    another_tool.description = "Another tool."
    another_tool.parameters = {
        "type": "object",
        "properties": {},
    }

    registry.register(another_tool)

    tools = registry.llm_tools(
        allowed_tools=["dummy_tool"]
    )

    assert len(tools) == 1
    assert tools[0].name == "dummy_tool"