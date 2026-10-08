"""External system connector interface (Job 19).

Real CRM/calendar/email connectors plug in later (Phase 13).
Runtime tools depend only on this abstraction so side effects stay mockable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass
class ExternalRecord:
    system: str
    record_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ExternalSystemClient(ABC):
    """Boundary between AI tools and external systems."""

    @abstractmethod
    def search(
        self,
        *,
        system: str,
        query: str,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def create(
        self,
        *,
        system: str,
        payload: dict[str, Any],
    ) -> ExternalRecord:
        raise NotImplementedError

    @abstractmethod
    def get(
        self,
        *,
        system: str,
        record_id: str,
    ) -> dict[str, Any] | None:
        raise NotImplementedError


class MockExternalSystemClient(ExternalSystemClient):
    """In-memory mock used by default domain tools."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, dict[str, Any]]] = {}

    def search(
        self,
        *,
        system: str,
        query: str,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        bucket = self._store.get(system, {})
        q = (query or "").lower()
        results = []
        for rec in bucket.values():
            blob = " ".join(str(v) for v in rec.values()).lower()
            if not q or q in blob:
                if filters:
                    ok = all(str(rec.get(k)) == str(v) for k, v in filters.items())
                    if not ok:
                        continue
                results.append(dict(rec))
        return results

    def create(
        self,
        *,
        system: str,
        payload: dict[str, Any],
    ) -> ExternalRecord:
        record_id = str(uuid4())
        data = {"id": record_id, **payload}
        self._store.setdefault(system, {})[record_id] = data
        return ExternalRecord(system=system, record_id=record_id, payload=data)

    def get(
        self,
        *,
        system: str,
        record_id: str,
    ) -> dict[str, Any] | None:
        return self._store.get(system, {}).get(record_id)


# Process-wide default mock (tests can replace)
_default_client: ExternalSystemClient = MockExternalSystemClient()


def get_external_client() -> ExternalSystemClient:
    return _default_client


def set_external_client(client: ExternalSystemClient) -> None:
    global _default_client
    _default_client = client
