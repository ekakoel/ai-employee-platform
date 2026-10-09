"""Job 39 — durable company inventory (availability rows in DB)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import CompanyInventory


def upsert_inventory_row(
    db: Session,
    *,
    company_id: str,
    system: str,
    external_key: str,
    payload: dict[str, Any],
) -> CompanyInventory:
    row = db.scalar(
        select(CompanyInventory).where(
            CompanyInventory.company_id == company_id,
            CompanyInventory.system == system,
            CompanyInventory.external_key == external_key,
        )
    )
    data = dict(payload)
    data.setdefault("company_id", company_id)
    data.setdefault("id", external_key)
    if row is None:
        row = CompanyInventory(
            company_id=company_id,
            system=system,
            external_key=external_key,
            payload=data,
            is_active=True,
        )
        db.add(row)
    else:
        row.payload = data
        row.is_active = True
    db.flush()
    return row


def list_inventory(
    db: Session,
    *,
    company_id: str,
    system: str = "availability",
    active_only: bool = True,
) -> list[dict[str, Any]]:
    q = select(CompanyInventory).where(
        CompanyInventory.company_id == company_id,
        CompanyInventory.system == system,
    )
    if active_only:
        q = q.where(CompanyInventory.is_active.is_(True))
    rows = list(db.scalars(q).all())
    out = []
    for r in rows:
        payload = dict(r.payload or {})
        payload.setdefault("id", r.external_key)
        payload.setdefault("company_id", company_id)
        out.append(payload)
    return out


def hydrate_connector_from_db(db: Session, company_id: str) -> int:
    """Push DB inventory into process mock connector."""
    from app.tools.connectors import get_external_client

    client = get_external_client()
    rows = list_inventory(db, company_id=company_id, system="availability")
    for row in rows:
        client.create(system="availability", payload=row)
    return len(rows)
