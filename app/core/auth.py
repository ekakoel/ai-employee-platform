"""Authentication dependencies — JWT Bearer + legacy X-User-ID."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import User


def _load_user(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if not user or getattr(user, "status", "active") != "active":
        raise HTTPException(status_code=401, detail="Invalid or inactive user")
    return user


def get_current_user(
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> User:
    """
    Resolve current user from:
    1. Authorization: Bearer <jwt>
    2. X-User-ID header (MVP / workspace compatibility)

    When auth_enabled=True in production, missing credentials → 401.
    """
    # Bearer JWT
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            payload = decode_access_token(token)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Token missing subject")
        return _load_user(db, user_id)

    # Legacy header
    if x_user_id:
        return _load_user(db, x_user_id)

    if settings.auth_enabled:
        raise HTTPException(
            status_code=401,
            detail="Authentication required (Bearer token or X-User-ID)",
        )
    raise HTTPException(status_code=401, detail="X-User-ID header is required")
