"""Job 29 — Integrations framework: webhook ingress, connectors, event mapping."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Integration, IntegrationStatus
from app.services.audit import record_audit
from app.services.automation import fire_event


SUPPORTED_TYPES = {"email_outbound", "calendar", "webhook_generic"}


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def verify_webhook_signature(
    *,
    secret_hash: str | None,
    raw_body: bytes,
    signature_header: str | None,
) -> bool:
    """
    HMAC-SHA256 over raw body, hex digest.
    Header forms accepted: 'sha256=<hex>' or bare '<hex>'.
    """
    if not secret_hash or not signature_header:
        return False
    sig = signature_header.strip()
    if sig.startswith("sha256="):
        sig = sig[len("sha256=") :]
    expected_plain = None
    # We only store hash of secret; recompute HMAC requires original secret.
    # For verification we compare HMAC using provided signature against
    # recomputation only when caller passes plaintext secret separately.
    # Here: secret_hash is sha256(secret); we need the secret for HMAC.
    # Design: store webhook_secret_hash as sha256(secret) for display safety,
    # but verification uses timing-safe compare of provided signature to
    # recomputed value when integration carries plaintext in config under
    # '_webhook_secret' for runtime (not returned by API).
    return False  # replaced by verify_with_secret


def verify_with_secret(
    *,
    secret: str,
    raw_body: bytes,
    signature_header: str | None,
) -> bool:
    if not secret or not signature_header:
        return False
    sig = signature_header.strip()
    if sig.lower().startswith("sha256="):
        sig = sig.split("=", 1)[1]
    digest = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(digest, sig)


def create_integration(
    db: Session,
    *,
    company_id: str,
    name: str,
    type: str,
    config: dict[str, Any] | None = None,
    event_map: dict[str, str] | None = None,
    webhook_secret: str | None = None,
) -> tuple[Integration, str | None]:
    """
    Create integration. Returns (entity, plaintext_webhook_secret_once).
    Plaintext secret is only returned at creation time.
    """
    itype = (type or "").strip().lower()
    if itype not in SUPPORTED_TYPES:
        raise ValueError(
            f"Unsupported integration type '{type}'. "
            f"Supported: {sorted(SUPPORTED_TYPES)}"
        )
    secret = webhook_secret or secrets.token_urlsafe(32)
    cfg = dict(config or {})
    # Keep runtime secret in config (API responses must strip it)
    cfg["_webhook_secret"] = secret

    integration = Integration(
        company_id=company_id,
        name=name[:200],
        type=itype,
        config=cfg,
        webhook_secret_hash=_hash_secret(secret),
        event_map=dict(event_map or {}),
        status=IntegrationStatus.ACTIVE.value,
    )
    db.add(integration)
    db.flush()
    return integration, secret


def public_view(integration: Integration) -> dict[str, Any]:
    cfg = dict(integration.config or {})
    cfg.pop("_webhook_secret", None)
    return {
        "id": integration.id,
        "company_id": integration.company_id,
        "name": integration.name,
        "type": integration.type,
        "config": cfg,
        "event_map": integration.event_map or {},
        "status": integration.status,
        "last_error": integration.last_error,
        "created_at": integration.created_at.isoformat()
        if integration.created_at
        else None,
        "has_webhook_secret": bool(integration.webhook_secret_hash),
    }


def handle_webhook(
    db: Session,
    *,
    company_id: str,
    integration_id: str,
    raw_body: bytes,
    signature_header: str | None,
    event_name: str | None = None,
) -> dict[str, Any]:
    integration = db.scalar(
        select(Integration).where(
            Integration.id == integration_id,
            Integration.company_id == company_id,
        )
    )
    if not integration:
        raise LookupError("Integration not found")
    if integration.status != IntegrationStatus.ACTIVE.value:
        raise PermissionError("Integration is not active")

    secret = (integration.config or {}).get("_webhook_secret") or ""
    if not verify_with_secret(
        secret=secret,
        raw_body=raw_body,
        signature_header=signature_header,
    ):
        record_audit(
            db,
            company_id=company_id,
            action="integration.webhook.rejected",
            resource_type="integration",
            resource_id=integration_id,
            status="denied",
            details={"reason": "bad_signature"},
        )
        raise PermissionError("Invalid webhook signature")

    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON body") from exc
    if not isinstance(payload, dict):
        payload = {"data": payload}

    external_event = (
        event_name
        or payload.get("event")
        or payload.get("type")
        or "webhook.received"
    )
    event_map = integration.event_map or {}
    automation_event = event_map.get(str(external_event), str(external_event))

    runs = fire_event(
        db,
        company_id=company_id,
        event_type=automation_event,
        payload={
            "integration_id": integration_id,
            "integration_type": integration.type,
            "external_event": external_event,
            **payload,
        },
        idempotency_key=f"wh:{integration_id}:{hashlib.sha256(raw_body).hexdigest()[:24]}",
    )

    record_audit(
        db,
        company_id=company_id,
        action="integration.webhook.accepted",
        resource_type="integration",
        resource_id=integration_id,
        status="success",
        details={
            "external_event": external_event,
            "automation_event": automation_event,
            "runs": len(runs),
        },
    )
    return {
        "accepted": True,
        "external_event": external_event,
        "automation_event": automation_event,
        "runs_triggered": len(runs),
        "run_ids": [r.id for r in runs],
    }


# --- Connector stubs ---

def email_outbound_send(
    integration: Integration,
    *,
    to: str,
    subject: str,
    body: str,
) -> dict[str, Any]:
    """Stub email connector — no real SMTP; returns payload for audit/tests."""
    if integration.type != "email_outbound":
        raise ValueError("Integration is not email_outbound")
    from_addr = (integration.config or {}).get("from_address") or "noreply@example.local"
    return {
        "status": "queued_stub",
        "from": from_addr,
        "to": to,
        "subject": subject,
        "body_preview": (body or "")[:200],
        "provider": (integration.config or {}).get("provider") or "stub",
    }


def calendar_stub_list_events(
    integration: Integration,
    *,
    days_ahead: int = 7,
) -> dict[str, Any]:
    if integration.type != "calendar":
        raise ValueError("Integration is not calendar")
    return {
        "status": "ok_stub",
        "calendar_id": (integration.config or {}).get("calendar_id") or "primary",
        "events": [],
        "days_ahead": days_ahead,
        "note": "Calendar connector stub — no external API call",
    }
