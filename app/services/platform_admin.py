"""Job 23 — Platform super-admin helpers (support tools)."""

from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.models.entities import User


def require_platform_admin(
    user: User = Depends(get_current_user),
) -> User:
    """Check persisted privileges on an authenticated, active user."""
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
