from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.entities import KnowledgeItem
from app.tools.base import BaseTool, ToolContext


class SearchContractTool(BaseTool):
    name = "search_contract"

    description = (
        "Search contract-related knowledge belonging to the current "
        "company and agent."
    )

    def __init__(self, db: Session):
        self.db = db

    def execute(
        self,
        context: ToolContext,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        query = str(arguments.get("query", "")).strip()

        if not query:
            raise ValueError(
                "search_contract requires a non-empty 'query'."
            )

        search_pattern = f"%{query}%"

        items = list(
            self.db.scalars(
                select(KnowledgeItem)
                .where(
                    KnowledgeItem.company_id == context.company_id,
                    KnowledgeItem.agent_instance_id == context.agent_instance_id,
                    KnowledgeItem.is_active.is_(True),
                    or_(
                        KnowledgeItem.title.ilike(search_pattern),
                        KnowledgeItem.content.ilike(search_pattern),
                        KnowledgeItem.category.ilike(search_pattern),
                    ),
                )
                .order_by(KnowledgeItem.created_at.desc())
            ).all()
        )

        return {
            "tool": self.name,
            "query": query,
            "count": len(items),
            "results": [
                {
                    "id": item.id,
                    "title": item.title,
                    "category": item.category,
                    "content": item.content,
                }
                for item in items
            ],
        }