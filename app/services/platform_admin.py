"""Job 23 — Platform super-admin helpers (support tools)."""

from __future__ import annotations

from fastapi import Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import User


def platform_admin_email_set() -> set[str]:
    raw = settings.platform_admin_emails or ""
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def sync_platform_admin_flag(db: Session, user: User) -> User:
    """Grant is_platform_admin if email is in PLATFORM_ADMIN_EMAILS."""
    emails = platform_admin_email_set()
    if user.email and user.email.lower() in emails and not user.is_platform_admin:
        user.is_platform_admin = True
        db.flush()
    return user


def require_platform_admin(
    db: Session,
    x_user_id: str | None,
) -> User:
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    user = db.get(User, x_user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid user")
    sync_platform_admin_flag(db, user)
    if not user.is_platform_admin:
        raise HTTPException(
            status_code=403,
            detail="Platform admin privileges required",
        )
    if user.status != "active":
        raise HTTPException(status_code=403, detail="User inactive")
    return user


def grant_platform_admin(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if not user:
        raise ValueError("User not found")
    user.is_platform_admin = True
    db.flush()
    return user
