"""Domain tools for reservation / knowledge (Job 19).

Side-effect tools call ExternalSystemClient; consult mode blocks them.
"""

from __future__ import annotations

from typing import Any
from datetime import date
from decimal import Decimal
import json
import re

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.knowledge.retrieval import search_knowledge_chunks
from app.models.entities import KnowledgeItem, Task
from app.tools.base import AgentTool, ToolContext
from app.tools.connectors import get_external_client


def company_prices(db: Session, context: ToolContext) -> dict[str, dict]:
    """Structured pricing records are authoritative; prose is not a price table."""
    rows = db.scalars(select(KnowledgeItem).where(
        KnowledgeItem.company_id == context.company_id, KnowledgeItem.is_active.is_(True),
        or_(KnowledgeItem.agent_instance_id.is_(None), KnowledgeItem.agent_instance_id == context.agent_instance_id),
        KnowledgeItem.category == "pricing",
    ))
    prices = {}
    for row in rows:
        try:
            payload = json.loads(row.content)
            for price in payload.get("prices", []):
                amount = Decimal(str(price["amount"]))
                if not amount.is_finite() or amount < 0:
                    continue
                key = f"{row.id}:{price['sku']}"
                prices[key] = {**price, "amount": str(amount), "source_id": f"knowledge:{row.id}"}
        except (ValueError, TypeError, KeyError, ArithmeticError, AttributeError):
            continue
    return prices


def availability_records(context: ToolContext, arguments: dict) -> list[dict]:
    start, end = str(arguments.get("check_in", "")), str(arguments.get("check_out", ""))
    if date.fromisoformat(start) >= date.fromisoformat(end):
        raise ValueError("Check-out must be after check-in.")
    records = get_external_client().search(system="availability", query="", filters={
        "company_id": context.company_id, "check_in": start, "check_out": end,
    })
    return [row for row in records if row.get("company_id") == context.company_id
            and row.get("check_in") == start and row.get("check_out") == end
            and row.get("available") is True
            and int(row.get("capacity", 0)) >= int(arguments.get("guests", 1))
            and (not arguments.get("location") or row.get("location") == arguments["location"])]


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
        options = availability_records(context, arguments)
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

    def __init__(self, db: Session):
        self.db = db

    def prepare_arguments(self, context: ToolContext, arguments: dict) -> dict:
        task = self.db.scalar(select(Task).where(
            Task.id == context.task_id, Task.company_id == context.company_id,
            Task.agent_instance_id == context.agent_instance_id,
        ))
        for key in ("guest_name", "check_in", "check_out"):
            value = arguments.get(key)
            if not isinstance(value, str) or not value or task is None or value.casefold() not in task.instruction.casefold():
                raise ValueError("Booking guest and dates must be supplied in the authorized task request.")
        selected = next((row for row in availability_records(context, arguments)
                         if row.get("id") == arguments.get("availability_id")), None)
        if not selected:
            raise ValueError("Verified company availability is required before booking.")
        amount = Decimal(str(selected["rate"]))
        if not amount.is_finite() or amount < 0 or not selected.get("currency"):
            raise ValueError("Company availability must include a valid rate and currency.")
        if "amount" in arguments and Decimal(str(arguments["amount"])) != amount:
            raise ValueError("Booking amount does not match company availability.")
        return {**arguments, "amount": str(amount), "currency": selected["currency"]}

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
                "availability_id": {"type": "string"},
            },
            "required": ["guest_name", "check_in", "check_out", "availability_id"],
        }

    def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        arguments = self.prepare_arguments(context, arguments)
        client = get_external_client()
        options = availability_records(context, arguments)
        selected = next((row for row in options if row.get("id") == arguments.get("availability_id")), None)
        if not selected:
            raise ValueError("Verified company availability is required before booking.")
        if arguments.get("amount") is not None and Decimal(str(arguments["amount"])) != Decimal(str(selected["rate"])):
            raise ValueError("Booking amount does not match verified company availability.")
        payload = {
            "company_id": context.company_id,
            "agent_instance_id": context.agent_instance_id,
            "guest_name": arguments.get("guest_name"),
            "check_in": arguments.get("check_in"),
            "check_out": arguments.get("check_out"),
            "room_type": selected["room_type"],
            "amount": selected["rate"],
            "currency": selected["currency"],
            "availability_id": selected["id"],
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
        if rec is not None and rec.get("company_id") != context.company_id:
            rec = None
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

    def __init__(self, db: Session):
        self.db = db

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
                            "price_id": {"type": "string"},
                            "quantity": {"type": "integer", "minimum": 1},
                        },
                    },
                },
                "currency": {"type": "string", "default": "USD"},
            },
            "required": ["customer", "items"],
        }

    def _validated_lines(self, context: ToolContext, arguments: dict[str, Any]):
        items = arguments.get("items") or []
        customer = arguments.get("customer")
        task = self.db.scalar(select(Task).where(
            Task.id == context.task_id, Task.company_id == context.company_id,
            Task.agent_instance_id == context.agent_instance_id,
        ))
        if not isinstance(customer, str) or not customer.strip() or task is None or customer.casefold() not in task.instruction.casefold():
            raise ValueError("Quotation customer must be supplied in the authorized task request.")
        if not items:
            raise ValueError("Quotation requires verified company pricing line items.")
        prices = company_prices(self.db, context)
        total = Decimal("0")
        lines = []
        references = []
        for it in items:
            price = prices.get(it.get("price_id"))
            if price is None:
                raise ValueError("Quotation line requires an accessible company price_id.")
            quantity = it.get("quantity", 1)
            if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
                raise ValueError("Quotation quantity must be a positive integer.")
            if quantity != 1 and str(quantity) not in re.findall(r"\d+", task.instruction):
                raise ValueError("Quotation quantity must be supplied in the task request.")
            if price.get("unit") == "guest":
                match = re.search(r"\b(\d+)\s+(?:guests?|people|persons?)\b", task.instruction, re.I)
                if not match or quantity != int(match.group(1)):
                    raise ValueError("Quotation quantity does not match the requested guest count.")
            if price.get("currency") != arguments.get("currency", "USD"):
                raise ValueError("Quotation currency must match the company price record.")
            amt = Decimal(price["amount"]) * quantity
            if "amount" in it and Decimal(str(it["amount"])) != amt:
                raise ValueError("Quotation amount does not match company pricing.")
            total += amt
            lines.append(f"- {price['description']} x {quantity}: {amt:.2f}")
            references.append({"source_id": price["source_id"], "price_id": it["price_id"], "quantity": quantity})
        currency = arguments.get("currency") or "USD"
        if "amount" in arguments and Decimal(str(arguments["amount"])) != total:
            raise ValueError("Policy amount does not match verified quotation total.")
        return lines, references, total, currency

    def prepare_arguments(self, context: ToolContext, arguments: dict) -> dict:
        _, _, total, currency = self._validated_lines(context, arguments)
        return {**arguments, "amount": str(total), "currency": currency}

    def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        lines, references, total, currency = self._validated_lines(context, arguments)
        customer = arguments.get("customer")
        body = (
            f"Quotation for {customer}\n"
            + "\n".join(lines)
            + f"\nTotal: {total:.2f} {currency}"
        )
        return {
            "tool": self.name,
            "customer": customer,
            "total": float(total),
            "currency": currency,
            "draft": body,
            "source_references": references,
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
            or item.agent_instance_id not in (None, context.agent_instance_id)
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
        CreateReservationTool(db),
        GetReservationTool(),
        DraftQuotationTool(db),
        SearchKnowledgeTool(db),
        ReadDocumentTool(db),
    ]
