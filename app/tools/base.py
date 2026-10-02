from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolContext:
    company_id: str
    agent_instance_id: str
    task_id: str | None = None


class BaseTool(ABC):
    name: str
    description: str

    @abstractmethod
    def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError
