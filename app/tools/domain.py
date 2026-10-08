"""Domain tools for reservation / knowledge (Job 19).

Side-effect tools call ExternalSystemClient; consult mode blocks them.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.knowledge.retrieval import search_knowledge_chunks
from app.models.entities import KnowledgeItem
from app.tools.base import AgentTool, ToolContext
from app.tools.connectors import get_external_client


class SearchAvailabilityTool(AgentTool):
    side_effect = False
    risk = "low"
    category = "reservation"

    @property
    def name(self) -> str:
        return "search_availability"

    @property
    def description(self) -> str:
        return "Search room/service availability for given dates and guests."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "check_in": {"type": "string", "description": "ISO date"},
                "check_out": {"type": "string", "description": "ISO date"},
                "guests": {"type": "integer", "default": 1},
                "location": {"type": "string"},
            },
            "required": ["check_in", "check_out"],
        }

    def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        check_in = str(arguments.get("check_in", "")).strip()
        check_out = str(arguments.get("check_out", "")).strip()
        guests = int(arguments.get("guests") or 1)
        location = str(arguments.get("location") or "default")
        # Deterministic mock inventory
        options = [
            {
                "room_type": "standard",
                "available": True,
                "rate": 75.0,
                "currency": "USD",
                "location": location,
            },
            {
                "room_type": "deluxe",
                "available": guests <= 3,
                "rate": 120.0,
                "currency": "USD",
                "location": location,
            },
        ]
        return {
            "tool": self.name,
            "check_in": check_in,
            "check_out": check_out,
            "guests": guests,
            "count": len(options),
            "options": options,
        }


class CreateReservationTool(AgentTool):
    side_effect = True
    risk = "high"
    category = "reservation"

    @property
    def name(self) -> str:
        return "create_reservation"

    @property
    def description(self) -> str:
        return "Create a reservation (side-effect: writes to booking system)."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "guest_name": {"type": "string"},
                "check_in": {"type": "string"},
                "check_out": {"type": "string"},
                "room_type": {"type": "string"},
                "amount": {"type": "number"},
            },
            "required": ["guest_name", "check_in", "check_out"],
        }

    def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        client = get_external_client()
        payload = {
            "company_id": context.company_id,
            "agent_instance_id": context.agent_instance_id,
            "guest_name": arguments.get("guest_name"),
            "check_in": arguments.get("check_in"),
            "check_out": arguments.get("check_out"),
            "room_type": arguments.get("room_type") or "standard",
            "amount": arguments.get("amount"),
            "status": "confirmed",
        }
        record = client.create(system="reservations", payload=payload)
        return {
            "tool": self.name,
            "side_effect": True,
            "reservation_id": record.record_id,
            "record": record.payload,
        }


class GetReservationTool(AgentTool):
    side_effect = False
    risk = "low"
    category = "reservation"

    @property
    def name(self) -> str:
        return "get_reservation"

    @property
    def description(self) -> str:
        return "Fetch a reservation by id (read-only)."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "reservation_id": {"type": "string"},
            },
            "required": ["reservation_id"],
        }

    def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        rid = str(arguments.get("reservation_id", "")).strip()
        client = get_external_client()
        rec = client.get(system="reservations", record_id=rid)
        return {
            "tool": self.name,
            "reservation_id": rid,
            "found": rec is not None,
            "record": rec,
        }


class DraftQuotationTool(AgentTool):
    side_effect = False
    risk = "low"
    category = "reservation"

    @property
    def name(self) -> str:
        return "draft_quotation"

    @property
    def description(self) -> str:
        return "Draft a quotation text from line items (no external write)."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "customer": {"type": "string"},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string"},
                            "amount": {"type": "number"},
                        },
                    },
                },
                "currency": {"type": "string", "default": "USD"},
            },
            "required": ["customer", "items"],
        }

    def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        items = arguments.get("items") or []
        total = 0.0
        lines = []
        for it in items:
            amt = float(it.get("amount") or 0)
            total += amt
            lines.append(f"- {it.get('description', 'item')}: {amt}")
        currency = arguments.get("currency") or "USD"
        customer = arguments.get("customer")
        body = (
            f"Quotation for {customer}\n"
            + "\n".join(lines)
            + f"\nTotal: {total:.2f} {currency}"
        )
        return {
            "tool": self.name,
            "customer": customer,
            "total": total,
            "currency": currency,
            "draft": body,
        }


class SearchKnowledgeTool(AgentTool):
    side_effect = False
    risk = "low"
    category = "knowledge"

    def __init__(self, db: Session):
        self.db = db

    @property
    def name(self) -> str:
        return "search_knowledge"

    @property
    def description(self) -> str:
        return "Semantic/keyword search over company knowledge chunks."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        }

    def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query", "")).strip()
        limit = int(arguments.get("limit") or 5)
        hits = search_knowledge_chunks(
            self.db,
            company_id=context.company_id,
            query=query,
            agent_instance_id=context.agent_instance_id,
            limit=limit,
        )
        return {
            "tool": self.name,
            "query": query,
            "count": len(hits),
            "results": hits,
        }


class SearchContractTool(AgentTool):
    """Existing contract knowledge search with metadata."""

    side_effect = False
    risk = "low"
    category = "contract"

    def __init__(self, db: Session):
        self.db = db

    @property
    def name(self) -> str:
        return "search_contract"

    @property
    def description(self) -> str:
        return (
            "Search contract-related knowledge belonging to the current "
            "company and agent."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Contract name, supplier, or keyword.",
                },
            },
            "required": ["query"],
        }

    def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query", "")).strip()
        if not query:
            raise ValueError("search_contract requires a non-empty 'query'.")
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


class ReadDocumentTool(AgentTool):
    side_effect = False
    risk = "low"
    category = "knowledge"

    def __init__(self, db: Session):
        self.db = db

    @property
    def name(self) -> str:
        return "read_document"

    @property
    def description(self) -> str:
        return "Read a knowledge item by id (read-only)."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"knowledge_item_id": {"type": "string"}},
            "required": ["knowledge_item_id"],
        }

    def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        kid = str(arguments.get("knowledge_item_id", "")).strip()
        item = self.db.get(KnowledgeItem, kid)
        if (
            not item
            or item.company_id != context.company_id
            or not item.is_active
        ):
            return {"tool": self.name, "found": False, "knowledge_item_id": kid}
        return {
            "tool": self.name,
            "found": True,
            "id": item.id,
            "title": item.title,
            "category": item.category,
            "content": item.content,
        }


def build_default_tools(db: Session) -> list[AgentTool]:
    return [
        SearchContractTool(db),
        SearchAvailabilityTool(),
        CreateReservationTool(),
        GetReservationTool(),
        DraftQuotationTool(),
        SearchKnowledgeTool(db),
        ReadDocumentTool(db),
    ]
