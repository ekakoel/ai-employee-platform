"""Job 20 — In-app notifications for approvals, delegations, task failures."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.entities import Notification, NotificationType, User


def emit_notification(
    db: Session,
    *,
    company_id: str,
    user_id: str,
    type: str,
    title: str,
    body: str = "",
    payload: dict[str, Any] | None = None,
) -> Notification | None:
    if not user_id:
        return None
    user = db.get(User, user_id)
    if not user or user.company_id != company_id:
        return None
    note = Notification(
        company_id=company_id,
        user_id=user_id,
        type=type,
        title=title[:300],
        body=body or "",
        payload=payload or {},
    )
    db.add(note)
    db.flush()
    return note


def notify_users(
    db: Session,
    *,
    company_id: str,
    user_ids: list[str],
    type: str,
    title: str,
    body: str = "",
    payload: dict[str, Any] | None = None,
) -> list[Notification]:
    created: list[Notification] = []
    seen: set[str] = set()
    for uid in user_ids:
        if not uid or uid in seen:
            continue
        seen.add(uid)
        n = emit_notification(
            db,
            company_id=company_id,
            user_id=uid,
            type=type,
            title=title,
            body=body,
            payload=payload,
        )
        if n:
            created.append(n)
    return created


def list_notifications(
    db: Session,
    *,
    company_id: str,
    user_id: str,
    unread_only: bool = False,
    limit: int = 50,
) -> list[Notification]:
    q = select(Notification).where(
        Notification.company_id == company_id,
        Notification.user_id == user_id,
    )
    if unread_only:
        q = q.where(Notification.read_at.is_(None))
    q = q.order_by(Notification.created_at.desc()).limit(min(limit, 200))
    return list(db.scalars(q).all())


def unread_count(
    db: Session,
    *,
    company_id: str,
    user_id: str,
) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.company_id == company_id,
                Notification.user_id == user_id,
                Notification.read_at.is_(None),
            )
        )
        or 0
    )


def mark_read(
    db: Session,
    *,
    company_id: str,
    user_id: str,
    notification_id: str,
) -> Notification | None:
    note = db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.company_id == company_id,
            Notification.user_id == user_id,
        )
    )
    if not note:
        return None
    if note.read_at is None:
        note.read_at = datetime.now(timezone.utc)
        db.flush()
    return note


def mark_all_read(
    db: Session,
    *,
    company_id: str,
    user_id: str,
) -> int:
    now = datetime.now(timezone.utc)
    result = db.execute(
        update(Notification)
        .where(
            Notification.company_id == company_id,
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=now)
    )
    return int(result.rowcount or 0)
