from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents.context import AgentContext, load_agent_context
from app.models.entities import AgentInstance, Task


class AgentContextBuilder:
    """
    Builds the runtime context for an AI Employee.

    Database access stays inside this layer.
    The LLM receives only the resulting AgentContext.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def build(
        self,
        agent: AgentInstance,
        task: Task | None = None,
    ) -> AgentContext:
        """
        Build context for an agent instance and optional task.
        """

        return load_agent_context(
            self.db,
            agent,
            task,
        )